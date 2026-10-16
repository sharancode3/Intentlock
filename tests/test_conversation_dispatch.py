"""Offline production-route checks with isolated stores and counted fake providers."""

import sqlite3

import httpx
import pytest

from backend.main import app, get_speech_input_port, get_speech_output_port, get_voice_evidence_port
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.core.ports import SpeechInputResult, SpeechOutputResult, VoiceEvidenceResult
from backend.core.scoped_authorization import ScopedAuthorizationService
from backend.services.ticket_knowledge_service import TicketKnowledgeService
from backend.services.conversation_dispatch import conversation_store
from backend.core.config import settings


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
    assert cto["result_block"]["payload"]["direct_count"] == 1
    assert cto["result_block"]["payload"]["descendant_count"] == 3
    restricted = await turn(speech, "EMP-4002", "Open RND-5002 details", cto["session"]["sessionId"], "private-descendant")
    assert restricted["status"] == "denied"
    assert restricted["result_block"]["type"] == "DENIAL_BANNER"
    assert voice.calls == 4


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
    assert voice.calls == 2


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
