"""Offline production-route checks with isolated stores and counted fake providers."""

import sqlite3
import asyncio

import httpx
import pytest

from backend.main import app, get_speech_input_port, get_speech_output_port, get_voice_evidence_port
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.core.ports import SpeechInputResult, SpeechOutputResult, VoiceEvidenceResult
from backend.core.scoped_authorization import ScopedAuthorizationService
from backend.services.ticket_knowledge_service import TicketKnowledgeService
from backend.services.conversation_dispatch import conversation_store
from backend.services.ticket_action_store import canonical as json_canonical
from backend.core.config import settings
from backend.services.conversation_dispatch import IntentPlan


class Speech:
    transcript = ""
    speech_seconds = 5.1

    async def transcribe(self, metadata, audio, turn_id):
        return SpeechInputResult(is_available=True, transcript=self.transcript,
                                 speech_duration_s=self.speech_seconds)


class Voice:
    def __init__(self):
        self.calls = 0
        self.decision = "match"
        self.authenticity = "real"
        self.speaker_override = None

    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        self.calls += 1
        return VoiceEvidenceResult(is_available=True, decision=self.decision,
            deepfake_verdict=self.authenticity, speaker_id=self.speaker_override or candidate_speaker_id, account_alias="test",
            audio_digest=audio_metadata.sha256_digest)


class SilentTTS:
    async def synthesize(self, text, turn_id):
        return SpeechOutputResult(is_available=True)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "APP_DB_PATH", str(tmp_path / "tickets.sqlite3"))
    mapping = IdentityMappingStore(str(tmp_path / "identity.sqlite3"))
    for employee_id in ("EMP-1001", "EMP-2001", "EMP-4002"):
        mapping.upsert_mapping(employee_id, f"speaker_{employee_id}", account_alias="test",
                               enrollment_status="ENROLLED")
    monkeypatch.setattr(IdentityMappingStore, "_instance", mapping)
    tickets = TicketKnowledgeService()
    scoped = ScopedAuthorizationService(ticket_service=tickets)
    monkeypatch.setattr(ScopedAuthorizationService, "_instance", scoped)
    speech, voice = Speech(), Voice()
    app.dependency_overrides[get_speech_input_port] = lambda: speech
    app.dependency_overrides[get_speech_output_port] = lambda: SilentTTS()
    app.dependency_overrides[get_voice_evidence_port] = lambda: voice
    yield speech, voice, tickets
    app.dependency_overrides.clear()
    conversation_store._states.clear()


async def turn(speech, actor, utterance, session=None, turn_id="turn-a"):
    speech.transcript = utterance
    form = {"client_turn_id": turn_id, "candidate_employee_id": actor}
    if session:
        form["session_id"] = session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/voice/turn", data=form,
            files={"audio_file": ("voice.wav", b"RIFF" + turn_id.encode() * 500, "audio/wav")})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_public_and_profile_route(rig):
    speech, voice, _ = rig
    public = await turn(speech, "EMP-1001", "What can you do?", turn_id="public")
    assert public["result_block"]["type"] == "PUBLIC_FAQ"
    assert voice.calls == 0
    own = await turn(speech, "EMP-1001", "Show my profile and projects", turn_id="own")
    assert own["result_block"]["type"] == "EMPLOYEE_PROFILE"
    assert own["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
    assert own["result_block"]["payload"]["employee"]["active_projects"]
    assert own["primary_result_id"] == own["result_block"]["id"]
    assert voice.calls == 1


@pytest.mark.asyncio
async def test_reporting_scope_and_drilldown(rig):
    speech, voice, _ = rig
    manager = await turn(speech, "EMP-2001", "Show my reporting tree", turn_id="tree-priya")
    payload = manager["result_block"]["payload"]
    assert manager["result_block"]["type"] == "ORG_TREE"
    assert payload["direct_count"] == 2
    assert {node["id"] for node in payload["nodes"]} == {"EMP-2001", "EMP-1001", "EMP-1501"}
    session = manager["session"]["sessionId"]
    detail = await turn(speech, "EMP-2001", "Open Aarav's details", session, "aarav-detail")
    assert detail["result_block"]["type"] == "EMPLOYEE_PROFILE"
    assert detail["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
    cto = await turn(speech, "EMP-4002", "Show everyone reporting to me", turn_id="tree-cto")
    assert cto["result_block"]["payload"]["direct_count"] in (1, 2)
    assert cto["result_block"]["payload"]["descendant_count"] in (3, 13)
    restricted = await turn(speech, "EMP-4002", "Open RND-5002 details", cto["session"]["sessionId"], "private-descendant")
    assert restricted["status"] == "denied"
    assert restricted["result_block"]["type"] == "DENIAL_BANNER"
    # Each actor authenticates once; subsequent reads still pass resource authorization.
    assert voice.calls == 2


@pytest.mark.asyncio
async def test_ticket_chart_uses_snapshot_without_extra_voice_call(rig):
    speech, voice, _ = rig
    first = await turn(speech, "EMP-2001", "Show my team's tickets", turn_id="tickets")
    assert first["result_block"]["type"] == "TICKET_LIST", first["assistant_message"]
    total = first["result_block"]["payload"]["total_count"]
    session = first["session"]["sessionId"]
    chart = await turn(speech, "EMP-2001", "Show those tickets as a bar chart", session, "bar")
    assert chart["result_block"]["type"] == "TEAM_METRIC_CHART", chart["assistant_message"]
    assert sum(point["count"] for point in chart["result_block"]["payload"]["data"]) == total
    pie = await turn(speech, "EMP-2001", "Pie by status instead", session, "pie")
    assert pie["result_block"]["payload"]["chart_type"] == "PIE"
    assert voice.calls == 1


@pytest.mark.asyncio
async def test_ticket_update_readback_commit_and_retry(rig):
    speech, voice, tickets = rig
    proposed = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", turn_id="proposal")
    assert proposed["result_block"]["type"] == "READBACK_CONFIRMATION"
    assert tickets.get_ticket_by_id("TKT-2026-001")["priority"] == "High"
    phrase = proposed["result_block"]["payload"]["draft"]["summary_readback"]
    session = proposed["session"]["sessionId"]
    committed = await turn(speech, "EMP-1001", phrase, session, "confirmation")
    assert committed["result_block"]["type"] == "ACTION_RECEIPT"
    receipt = committed["result_block"]["payload"]["receipt"]
    assert receipt["storage"] == "SQLite" and receipt["version"] == 2
    assert tickets.get_ticket_by_id("TKT-2026-001")["priority"] == "Critical"
    retried = await turn(speech, "EMP-1001", phrase, session, "confirmation-retry")
    assert retried["result_block"]["payload"]["receipt"]["event_id"] == receipt["event_id"]
    assert voice.calls == 3


@pytest.mark.asyncio
async def test_short_private_phrase_and_exact_delivery_retry(rig):
    speech, voice, _ = rig
    speech.speech_seconds = 2.0
    short = await turn(speech, "EMP-1001", "Show my profile", turn_id="short")
    assert short["status"] == "clarification" and voice.calls == 0
    speech.speech_seconds = 5.1
    first = await turn(speech, "EMP-1001", "Show my profile", turn_id="retryable")
    again = await turn(speech, "EMP-1001", "Show my profile", turn_id="retryable")
    assert first["result_block"]["id"] == again["result_block"]["id"]
    assert voice.calls == 1


@pytest.mark.asyncio
async def test_wrong_speaker_fails_closed_and_cancel_discards_draft(rig):
    speech, voice, tickets = rig
    voice.decision = "no_match"
    denied = await turn(speech, "EMP-1001", "Show my profile", turn_id="wrong-speaker")
    assert denied["status"] == "denied" and denied["session"]["state"] == "ANONYMOUS"
    voice.decision = "match"
    proposed = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", turn_id="to-cancel")
    session = proposed["session"]["sessionId"]
    cancelled = await turn(speech, "EMP-1001", "Cancel", session, "cancelled")
    assert "cancelled" in cancelled["assistant_message"].lower()
    phrase = proposed["result_block"]["payload"]["draft"]["summary_readback"]
    later = await turn(speech, "EMP-1001", phrase, session, "too-late")
    assert later["status"] == "denied"
    assert tickets.get_ticket_by_id("TKT-2026-001")["priority"] == "High"


@pytest.mark.asyncio
async def test_date_filter_and_real_creation_trend(rig):
    speech, _, _ = rig
    response = await turn(speech, "EMP-2001", "Show tickets created since 2026-10-12 as a line chart", turn_id="trend")
    assert response["result_block"]["type"] == "TEAM_METRIC_CHART"
    chart = response["result_block"]["payload"]
    assert chart["chart_type"] == "LINE"
    assert all(point["label"] >= "2026-10-12" for point in chart["data"])
    assert sum(point["count"] for point in chart["data"]) == chart["kpis"]["total_tickets"]


@pytest.mark.asyncio
async def test_create_ticket_requires_fresh_exact_confirmation(rig):
    speech, _, tickets = rig
    before = len(tickets.list_all_tickets())
    proposed = await turn(speech, "EMP-1001", "Create a ticket titled Printer queue fails on floor three", turn_id="create-propose")
    assert proposed["result_block"]["type"] == "READBACK_CONFIRMATION"
    assert len(tickets.list_all_tickets()) == before
    session = proposed["session"]["sessionId"]
    phrase = proposed["result_block"]["payload"]["draft"]["summary_readback"]
    committed = await turn(speech, "EMP-1001", phrase, session, "create-confirm")
    receipt = committed["result_block"]["payload"]["receipt"]
    assert receipt["status"] == "COMMITTED" and receipt["resource_id"].startswith("TKT-2026-")
    assert len(tickets.list_all_tickets()) == before + 1


@pytest.mark.asyncio
async def test_result_actions_use_delivered_source_and_voice_for_new_detail(rig):
    speech, voice, _ = rig
    tree = await turn(speech, "EMP-2001", "Show my reporting tree", turn_id="click-tree")
    session = tree["session"]["sessionId"]
    source = tree["result_block"]["id"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        action = {"action": "open_profile", "source_result_id": source, "target_id": "EMP-1001"}
        headers = {"Authorization": f"Bearer {session}"}
        first = await client.post("/api/v1/voice/result-action", json=action, headers=headers)
        assert first.status_code == 409 and first.json()["status"] == "verification_required"
        outside = await client.post("/api/v1/voice/result-action", json={**action, "target_id": "EMP-3001"}, headers=headers)
        assert outside.status_code == 403
    detail = await turn(speech, "EMP-2001", "Open the first person", session, "click-voice-detail")
    assert detail["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        cached = await client.post("/api/v1/voice/result-action", json=action, headers=headers)
        assert cached.status_code == 200
        assert cached.json()["result_block"]["id"] == detail["result_block"]["id"]
    assert voice.calls == 1  # Voice follow-up reuses the valid session; scope is rechecked.


@pytest.mark.asyncio
async def test_provider_inconclusive_and_speaker_mismatch_fail_closed(rig):
    speech, voice, _ = rig
    voice.authenticity = "not_sure"
    unsure = await turn(speech, "EMP-1001", "Show my profile", turn_id="inconclusive")
    assert unsure["status"] == "denied" and "inconclusive" in unsure["assistant_message"].lower()
    voice.authenticity = "real"
    voice.speaker_override = "speaker_other"
    mismatch = await turn(speech, "EMP-1001", "Show my profile", turn_id="speaker-mismatch")
    assert mismatch["status"] == "denied" and mismatch["session"]["state"] == "ANONYMOUS"
    assert voice.calls == 2


@pytest.mark.asyncio
async def test_short_private_followup_reuses_session_but_keeps_scope(rig):
    speech, voice, _ = rig
    entry = await turn(speech, "EMP-2001", "Show my reporting tree", turn_id="short-session-entry")
    speech.speech_seconds = 1.2
    detail = await turn(speech, "EMP-2001", "Show Aarav's profile", entry["session"]["sessionId"], "short-session-read")
    assert detail["status"] == "success"
    assert detail["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
    assert voice.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,mode", [("speaker_check", "speaker"), ("authenticity_check", "deepfake")])
async def test_standalone_check_uses_one_mode_without_authenticating(rig, monkeypatch, operation, mode):
    import backend.main as gateway
    from unittest.mock import AsyncMock
    speech, _, _ = rig
    modes = []
    class Diagnostic:
        async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id, mode):
            modes.append(mode)
            return VoiceEvidenceResult(is_available=True, decision="match" if mode == "speaker" else None,
                deepfake_verdict="real" if mode == "deepfake" else None,
                speaker_id=candidate_speaker_id, account_alias="test")
    app.dependency_overrides[get_voice_evidence_port] = lambda: Diagnostic()
    monkeypatch.setattr(gateway, "interpret_request", AsyncMock(return_value=IntentPlan(operation=operation)))
    response = await turn(speech, "EMP-1001", "Check this recording", turn_id=f"diagnostic-{mode}")
    assert response["status"] == "success"
    assert modes == [mode]
    assert response["session"]["state"] == "ANONYMOUS"
    assert response["trust_evidence"]["is_dual_verified"] is False
    assert not response["result_block"]["isSensitive"]


@pytest.mark.asyncio
async def test_missing_provider_enrollment_blocks_paid_verification(rig):
    from backend.adapters.detectif_adapter import DetectifHTTPClient, DetectifVoiceEvidenceAdapter
    speech, _, _ = rig
    requests = []
    def handler(request):
        requests.append(request.method)
        return httpx.Response(404, json={"error": {"code": "speaker_not_found"}})
    client = DetectifHTTPClient(api_key=None, combined_api_key="combined-test", transport=httpx.MockTransport(handler))
    adapter = DetectifVoiceEvidenceAdapter(client, account_alias="test")
    app.dependency_overrides[get_voice_evidence_port] = lambda: adapter
    for i in range(2):
        response = await turn(speech, "EMP-1001", "Show my profile", turn_id=f"missing-enrollment-{i}")
        assert response["session"]["state"] == "ANONYMOUS"
        assert response["error"]["code"] == "DETECTIF_UNAVAILABLE"
    assert requests == ["GET"]  # No combined POST, no fallback to any other credential.
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_duplicate_inflight_turns_coalesce_and_release_on_failure(rig, monkeypatch, fail):
    speech, voice, _ = rig
    began, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def transcribe(*_):
        calls.append(1)
        began.set()
        await release.wait()
        if fail:
            return SpeechInputResult(is_available=False, error_message="NO_SPEECH_DETECTED")
        return SpeechInputResult(is_available=True, transcript="Show my profile", speech_duration_s=5.2)
    monkeypatch.setattr(speech, "transcribe", transcribe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def post():
            return await client.post("/api/v1/voice/turn", data={"client_turn_id": f"duplicate-{fail}",
                "candidate_employee_id": "EMP-1001"}, files={"audio_file": ("voice.wav", b"RIFF" * 1000, "audio/wav")})
        first = asyncio.create_task(post())
        await asyncio.wait_for(began.wait(), 3)
        import hashlib
        import backend.main as gateway
        key = "voice_" + hashlib.sha256(f"duplicate-{fail}|EMP-1001|".encode()).hexdigest()
        waiting = gateway._in_flight_turns[key]
        original_wait = waiting.wait
        joined = asyncio.Event()
        async def wait_for_original():
            joined.set()
            await original_wait()
        monkeypatch.setattr(waiting, "wait", wait_for_original)
        second = asyncio.create_task(post())
        await asyncio.wait_for(joined.wait(), 3)
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(first, second), 3)
    assert calls == [1]
    assert sorted(response.status_code for response in responses) == ([400, 503] if fail else [200, 200])
    assert voice.calls == (0 if fail else 1)


@pytest.mark.asyncio
async def test_mentioning_target_id_does_not_change_actor(rig):
    speech, voice, _ = rig
    response = await turn(speech, "EMP-2001", "Open EMP-1001 details", turn_id="target-id")
    assert response["status"] == "success"
    assert response["session"]["actor"]["employeeId"] == "EMP-2001"
    assert response["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
    assert voice.calls == 1


@pytest.mark.asyncio
async def test_stale_ticket_version_cannot_commit(rig):
    speech, _, tickets = rig
    proposal = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", turn_id="stale-propose")
    session = proposal["session"]["sessionId"]
    phrase = proposal["result_block"]["payload"]["draft"]["summary_readback"]
    with sqlite3.connect(tickets.store.db_path) as conn:
        conn.execute("UPDATE tickets SET version=version+1 WHERE ticket_id=?", ("TKT-2026-001",))
    denied = await turn(speech, "EMP-1001", phrase, session, "stale-confirm")
    assert denied["status"] == "denied"
    assert tickets.get_ticket_by_id("TKT-2026-001")["priority"] == "High"
    with sqlite3.connect(tickets.store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM action_events").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_unresolved_and_negated_status_filters(rig):
    speech, voice, _ = rig
    # 1. "Show unresolved tickets" must exclude Resolved and Closed
    unresolved = await turn(speech, "EMP-2001", "Show unresolved tickets", turn_id="unresolved")
    assert unresolved["result_block"]["type"] == "TICKET_LIST"
    tickets_data = unresolved["result_block"]["payload"]["tickets"]
    assert len(tickets_data) > 0
    for t in tickets_data:
        assert t["status"].lower() not in ("resolved", "closed")

    # 2. "Show not resolved tickets" must also exclude Resolved and Closed
    session = unresolved["session"]["sessionId"]
    not_resolved = await turn(speech, "EMP-2001", "Show not resolved tickets", session, "not-resolved")
    tickets_nr = not_resolved["result_block"]["payload"]["tickets"]
    assert len(tickets_nr) == len(tickets_data)
    for t in tickets_nr:
        assert t["status"].lower() not in ("resolved", "closed")

    # 3. "Show not closed tickets" must exclude Closed but can include Resolved
    not_closed = await turn(speech, "EMP-2001", "Show not closed tickets", session, "not-closed")
    tickets_nc = not_closed["result_block"]["payload"]["tickets"]
    for t in tickets_nc:
        assert t["status"].lower() != "closed"
    assert any(t["status"].lower() == "resolved" for t in tickets_nc)


@pytest.mark.asyncio
async def test_followup_filtered_rechart(rig):
    speech, voice, _ = rig
    first = await turn(speech, "EMP-2001", "Show my team's tickets", turn_id="tickets-all")
    assert first["result_block"]["type"] == "TICKET_LIST"
    total_count = first["result_block"]["payload"]["total_count"]
    assert total_count == 35
    session = first["session"]["sessionId"]

    # Follow up asking for only high priority tickets as a pie chart instead
    chart = await turn(speech, "EMP-2001", "Show only high priority tickets as a pie chart instead", session, "pie-high")
    assert chart["result_block"]["type"] == "TEAM_METRIC_CHART"
    payload = chart["result_block"]["payload"]
    assert payload["chart_type"] == "PIE"
    chart_total = sum(item["count"] for item in payload["data"])
    # High priority tickets count is 12 (not all 35)
    assert chart_total == 12
    assert chart_total < total_count
    # Presentation-only switch with preserved filter to table
    table = await turn(speech, "EMP-2001", "Table instead", session, "table-instead")
    assert table["result_block"]["type"] == "TICKET_LIST"
    assert table["result_block"]["payload"]["total_count"] == 12


@pytest.mark.asyncio
async def test_target_resolution_and_sla_analytics(rig):
    speech, voice, _ = rig
    # 1. "Show my manager profile": EMP-2001's manager is EMP-4002.
    # Policy must deny access to manager's private profile, never substitute self!
    mgr = await turn(speech, "EMP-2001", "Show my manager profile", turn_id="mgr-profile")
    assert mgr["status"] == "denied"
    assert mgr["result_block"]["type"] == "DENIAL_BANNER"

    # 2. "Show EMP-1001 tickets": filters authorized tickets to EMP-1001
    emp_tickets = await turn(speech, "EMP-2001", "Show EMP-1001 tickets", turn_id="emp-tickets")
    assert emp_tickets["result_block"]["type"] == "TICKET_LIST"
    t_list = emp_tickets["result_block"]["payload"]["tickets"]
    assert len(t_list) < 35
    for t in t_list:
        assert t["assigned_to"] == "EMP-1001" or t.get("owner_id") == "EMP-1001"

    # 3. Overdue tickets metric
    overdue = await turn(speech, "EMP-2001", "How many overdue tickets?", turn_id="overdue")
    assert overdue["result_block"]["type"] == "TEAM_METRIC_CHART"
    assert "overdue" in overdue["result_block"]["title"].lower()
    assert "overdue" in overdue["assistant_message"].lower()

    # 4. SLA compliance metric
    sla = await turn(speech, "EMP-2001", "Show ticket SLA compliance", turn_id="sla")
    assert sla["result_block"]["type"] == "TEAM_METRIC_CHART"
    assert "sla" in sla["result_block"]["title"].lower()


@pytest.mark.asyncio
async def test_ticket_selection_click_and_voice_context(rig):
    speech, voice, tickets = rig
    first = await turn(speech, "EMP-1001", "Show my tickets", turn_id="t-list")
    session = first["session"]["sessionId"]
    source_id = first["result_block"]["id"]

    # Select a ticket via click action
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        action = {"action": "select_ticket", "source_result_id": source_id, "target_id": "TKT-2026-001"}
        headers = {"Authorization": f"Bearer {session}"}
        res = await client.post("/api/v1/voice/result-action", json=action, headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "success"

        # Selecting invalid target outside result returns 403
        bad = await client.post("/api/v1/voice/result-action", json={**action, "target_id": "TKT-9999-999"}, headers=headers)
        assert bad.status_code == 403

    # Subsequent voice turn in same session resolves "this ticket" to TKT-2026-001
    proposed = await turn(speech, "EMP-1001", "Change this ticket priority to Critical", session, "voice-change")
    assert proposed["result_block"]["type"] == "READBACK_CONFIRMATION"
    assert proposed["result_block"]["payload"]["draft"]["target"] == "TKT-2026-001"

    # Context comments also resolve without repeating ticket ID
    proposed_comment = await turn(speech, "EMP-1001", "Add a comment saying Investigating race condition", session, "voice-comment")
    assert proposed_comment["result_block"]["type"] == "READBACK_CONFIRMATION"
    assert proposed_comment["result_block"]["payload"]["draft"]["target"] == "TKT-2026-001"


@pytest.mark.asyncio
async def test_concurrent_ticket_creation_proposals_allocate_distinct_ids(rig):
    speech, voice, tickets = rig
    # Actor 1 proposes ticket creation
    prop1 = await turn(speech, "EMP-1001", "Create a ticket titled First network outage in floor 2", turn_id="create-1")
    assert prop1["result_block"]["type"] == "READBACK_CONFIRMATION"
    id1 = prop1["result_block"]["payload"]["draft"]["target"]
    sess1 = prop1["session"]["sessionId"]
    readback1 = prop1["result_block"]["payload"]["draft"]["summary_readback"]

    # Actor 2 proposes ticket creation while Actor 1 proposal is still PENDING
    prop2 = await turn(speech, "EMP-2001", "Create a ticket titled Second database latency in primary cluster", turn_id="create-2")
    assert prop2["result_block"]["type"] == "READBACK_CONFIRMATION"
    id2 = prop2["result_block"]["payload"]["draft"]["target"]
    sess2 = prop2["session"]["sessionId"]
    readback2 = prop2["result_block"]["payload"]["draft"]["summary_readback"]

    # Distinct ticket IDs must be reserved
    assert id1 != id2

    # Both confirmations commit without UNIQUE constraint conflict
    commit1 = await turn(speech, "EMP-1001", readback1, sess1, "confirm-1")
    assert commit1["result_block"]["type"] == "ACTION_RECEIPT"
    assert commit1["result_block"]["payload"]["receipt"]["resource_id"] == id1

    commit2 = await turn(speech, "EMP-2001", readback2, sess2, "confirm-2")
    assert commit2["result_block"]["type"] == "ACTION_RECEIPT"
    assert commit2["result_block"]["payload"]["receipt"]["resource_id"] == id2


@pytest.mark.asyncio
async def test_manifest_integrity_tampering_rejected(rig):
    speech, voice, tickets = rig
    proposal = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", turn_id="tamper-propose")
    session = proposal["session"]["sessionId"]
    phrase = proposal["result_block"]["payload"]["draft"]["summary_readback"]

    # Tamper with the parameters stored in action_drafts SQLite table (simulate internal modification)
    with sqlite3.connect(tickets.store.db_path) as conn:
        conn.execute("UPDATE action_drafts SET parameters=? WHERE session_id=?",
                     (json_canonical({"field": "priority", "value": "Low"}), session))

    # Confirmation must fail verification because canonical manifest hash mismatch is caught
    denied = await turn(speech, "EMP-1001", phrase, session, "tamper-confirm")
    assert denied["status"] == "denied"
    assert "integrity" in denied["assistant_message"].lower() or "modified" in denied["assistant_message"].lower()
    # Verify ticket was not modified
    assert tickets.get_ticket_by_id("TKT-2026-001")["priority"] == "High"
