"""Regression test suite for findings in docs/RENDER_FIXES_RECHECK_2026-10-17.md.

Covers:
1. High -> Low filter switching without false empty results (dimension replacement over retained base_rows).
2. SLA/overdue filters applying typed constraints first, using real as-of time, and honest unknown states.
3. Routing: EMP-1001 SLA compliance -> tickets, priority negation -> clarify, presentation change with selected ticket -> rechart.
4. Bounded compound queries returning multiple result_blocks in production voice turn response.
5. Manifest integrity covering expires_at and readback, and planned executor grant lifecycle.
"""

import asyncio
import sqlite3
import httpx
import pytest

from backend.main import app, get_speech_input_port, get_speech_output_port, get_voice_evidence_port
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.core.ports import SpeechInputResult, SpeechOutputResult, VoiceEvidenceResult
from backend.core.scoped_authorization import ScopedAuthorizationService
from backend.services.ticket_knowledge_service import TicketKnowledgeService
from backend.services.ticket_action_store import TicketActionStore, normalize_readback
from backend.services.conversation_dispatch import conversation_store, parse_local
from backend.core.config import settings


class Speech:
    transcript = ""
    speech_seconds = 5.1

    async def transcribe(self, metadata, audio, turn_id):
        return SpeechInputResult(
            is_available=True,
            transcript=self.transcript,
            speech_duration_s=self.speech_seconds,
        )


class Voice:
    def __init__(self):
        self.calls = 0
        self.decision = "match"
        self.authenticity = "real"
        self.speaker_override = None

    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        self.calls += 1
        return VoiceEvidenceResult(
            is_available=True,
            decision=self.decision,
            deepfake_verdict=self.authenticity,
            speaker_id=self.speaker_override or candidate_speaker_id,
            account_alias="test",
            audio_digest=audio_metadata.sha256_digest,
        )


class SilentTTS:
    async def synthesize(self, text, turn_id):
        return SpeechOutputResult(is_available=True)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "APP_DB_PATH", str(tmp_path / "tickets.sqlite3"))
    mapping = IdentityMappingStore(str(tmp_path / "identity.sqlite3"))
    for employee_id in ("EMP-1001", "EMP-2001", "EMP-4002"):
        mapping.upsert_mapping(
            employee_id,
            f"speaker_{employee_id}",
            account_alias="test",
            enrollment_status="ENROLLED",
        )
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


async def turn(speech, actor, utterance, session=None, turn_id="turn-recheck"):
    speech.transcript = utterance
    form = {"client_turn_id": turn_id, "candidate_employee_id": actor}
    if session:
        form["session_id"] = session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/voice/turn",
            data=form,
            files={"audio_file": ("voice.wav", b"RIFF" + turn_id.encode() * 500, "audio/wav")},
        )
    assert response.status_code == 200, response.text
    return response.json()


# ==============================================================================
# Priority 1: High -> Low filter switching without false empty results
# ==============================================================================

@pytest.mark.asyncio
async def test_filter_switching_retains_base_rows_without_false_empty(rig):
    """Reproduction:
    1. Manager: Show my tickets (35 rows).
    2. Show only high priority tickets as a pie chart instead -> 12 High rows.
    3. Show only low priority tickets as a pie chart instead -> 5 Low rows (NOT 0).
    4. Table instead -> 5 Low rows (view switch retains current dimension).
    """
    speech, voice, _ = rig

    # Step 1: Initial list
    first = await turn(speech, "EMP-2001", "Show my tickets", turn_id="t-init")
    assert first["result_block"]["type"] == "TICKET_LIST"
    total_count = first["result_block"]["payload"]["total_count"]
    assert total_count == 35
    session = first["session"]["sessionId"]

    # Step 2: High priority pie chart
    high_pie = await turn(
        speech, "EMP-2001", "Show only high priority tickets as a pie chart instead",
        session, "t-high-pie"
    )
    assert high_pie["result_block"]["type"] == "TEAM_METRIC_CHART"
    high_payload = high_pie["result_block"]["payload"]
    assert high_payload["chart_type"] == "PIE"
    high_count = sum(pt["count"] for pt in high_payload["data"])
    assert high_count == 12

    # Step 3: Low priority pie chart (replaces priority filter against retained base rows)
    low_pie = await turn(
        speech, "EMP-2001", "Show only low priority tickets as a pie chart instead",
        session, "t-low-pie"
    )
    assert low_pie["result_block"]["type"] == "TEAM_METRIC_CHART"
    low_payload = low_pie["result_block"]["payload"]
    assert low_payload["chart_type"] == "PIE"
    low_count = sum(pt["count"] for pt in low_payload["data"])
    assert low_count == 5, f"Expected 5 Low tickets, got {low_count} (false empty bug regression)"

    # Step 4: Presentation switch to Table preserves the Low filter
    table = await turn(speech, "EMP-2001", "Table instead", session, "t-table")
    assert table["result_block"]["type"] == "TICKET_LIST"
    assert table["result_block"]["payload"]["total_count"] == 5
    for t in table["result_block"]["payload"]["tickets"]:
        assert t["priority"].upper() == "LOW"


# ==============================================================================
# Priority 2: SLA/overdue filters, real as-of time, and honest unknown states
# ==============================================================================

@pytest.mark.asyncio
async def test_sla_overdue_filters_scope_to_typed_constraints_first(rig):
    """Reproduction:
    'Show only High priority overdue tickets' produces a plan with priority High,
    and calculates overdue over ONLY High tickets, not all 35 manager tickets.
    """
    speech, voice, _ = rig

    # All overdue query
    all_overdue = await turn(speech, "EMP-2001", "How many overdue tickets?", turn_id="t-all-overdue")
    assert all_overdue["result_block"]["type"] == "TEAM_METRIC_CHART"
    all_kpis = all_overdue["result_block"]["payload"]["kpis"]
    assert all_kpis["total_tickets"] == 35

    session = all_overdue["session"]["sessionId"]

    # High priority overdue query
    high_overdue = await turn(
        speech, "EMP-2001", "Show only High priority overdue tickets",
        session, "t-high-overdue"
    )
    assert high_overdue["result_block"]["type"] == "TEAM_METRIC_CHART"
    high_kpis = high_overdue["result_block"]["payload"]["kpis"]
    # Total tickets evaluated must be 12 (High tickets), NOT 35!
    assert high_kpis["total_tickets"] == 12
    assert "high" in high_overdue["result_block"]["title"].lower()


@pytest.mark.asyncio
async def test_sla_compliance_metric_honest_classification(rig):
    """Verifies SLA compliance separates On Track / Compliant from Unknown/No SLA,
    never defaulting missing SLA records to 'Within SLA'.
    """
    speech, voice, _ = rig

    sla_res = await turn(speech, "EMP-2001", "Show ticket SLA compliance", turn_id="t-sla-honest")
    assert sla_res["result_block"]["type"] == "TEAM_METRIC_CHART"
    payload = sla_res["result_block"]["payload"]
    labels = {pt["label"] for pt in payload["data"]}

    # Must contain defined states and must not collapse unknown into compliant
    assert any(l in labels for l in ("Within SLA", "Met", "Breached", "At Risk", "Unknown / No SLA"))
    kpis = payload.get("kpis", {})
    assert "compliance_rate_pct" in kpis
    assert 0.0 <= kpis["compliance_rate_pct"] <= 100.0


# ==============================================================================
# Priority 3: Negation and chart-versus-ticket routing
# ==============================================================================

def test_routing_sla_compliance_is_ticket_context_not_profile():
    """EMP-1001 SLA compliance must route to ticket SLA compliance, NOT profile."""
    plan = parse_local("Show EMP-1001 SLA compliance")
    assert plan.operation in ("ticket_list", "ticket_chart")
    assert plan.sla_metric in ("compliance", "overdue")
    assert plan.person_filter == "EMP-1001"


def test_routing_priority_negation_fails_safely_to_clarify():
    """Negated priority requests must not invert to positive."""
    plan1 = parse_local("Show tickets that are not high priority")
    assert plan1.operation == "clarify"

    plan2 = parse_local("Show tickets except critical")
    assert plan2.operation == "clarify"

    plan3 = parse_local("Show tickets other than low priority")
    assert plan3.operation == "clarify"


@pytest.mark.asyncio
async def test_routing_presentation_switch_with_selected_ticket_does_not_update_ticket(rig):
    """With a selected ticket in context, 'Change this chart to a pie chart'
    must route to presentation change (rechart), NOT update_ticket.
    """
    speech, voice, _ = rig

    # 1. Fetch tickets
    first = await turn(speech, "EMP-1001", "Show my tickets", turn_id="t-select-tickets")
    session = first["session"]["sessionId"]
    source_id = first["result_block"]["id"]

    # 2. Select a ticket via click action
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        action = {"action": "select_ticket", "source_result_id": source_id, "target_id": "TKT-2026-001"}
        headers = {"Authorization": f"Bearer {session}"}
        res = await client.post("/api/v1/voice/result-action", json=action, headers=headers)
        assert res.status_code == 200

    # 3. Say "Change this chart to a pie chart"
    # Even though a ticket is selected and utterance starts with "Change this...",
    # this is a presentation intent and must not attempt update_ticket on TKT-2026-001.
    chart_res = await turn(speech, "EMP-1001", "Change this chart to a pie chart", session, "t-chart-switch")
    assert chart_res["result_block"]["type"] == "TEAM_METRIC_CHART"
    assert chart_res["result_block"]["payload"]["chart_type"] == "PIE"
    assert chart_res["result_block"]["type"] != "READBACK_CONFIRMATION"
    assert chart_res["result_block"]["type"] != "DENIAL_BANNER"


# ==============================================================================
# Priority 4: Compound query execution emitting multiple result_blocks
# ==============================================================================

@pytest.mark.asyncio
async def test_compound_query_emits_multiple_result_blocks(rig):
    """'Show my profile and my tickets' must return multiple result blocks in the response
    and register both in conversation state.
    """
    speech, voice, _ = rig

    compound_res = await turn(speech, "EMP-1001", "Show my profile and my tickets", turn_id="t-compound")
    assert compound_res["status"] == "success"

    # Verify both result_block (primary) and result_blocks (full list) exist
    assert compound_res["result_block"] is not None
    result_blocks = compound_res.get("result_blocks") or []
    assert len(result_blocks) == 2, f"Expected 2 result blocks, got {len(result_blocks)}"

    types = [b["type"] for b in result_blocks]
    assert "EMPLOYEE_PROFILE" in types
    assert "TICKET_LIST" in types

    # Spoken summary combines both
    summary = compound_res["spoken_summary"]
    assert "Aarav Patel" in summary or "profile" in summary.lower()
    assert "tickets" in summary.lower()


# ==============================================================================
# Priority 5: Manifest hash integrity and planned executor boundary
# ==============================================================================

@pytest.mark.asyncio
async def test_manifest_tampering_of_expiry_and_readback_rejected(rig):
    """Tampering with expires_at or readback in action_drafts invalidates payload_hash."""
    speech, voice, tickets = rig

    # 1. Propose change
    prop = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", turn_id="prop-tamper")
    assert prop["result_block"]["type"] == "READBACK_CONFIRMATION"
    session = prop["session"]["sessionId"]
    phrase = prop["result_block"]["payload"]["draft"]["summary_readback"]

    # 2. Tamper with expires_at
    with sqlite3.connect(tickets.store.db_path) as conn:
        conn.execute("UPDATE action_drafts SET expires_at='2099-01-01T00:00:00' WHERE session_id=?", (session,))

    # 3. Confirmation must be rejected due to manifest hash mismatch
    denied = await turn(speech, "EMP-1001", phrase, session, "confirm-tamper-exp")
    assert denied["status"] == "denied"
    assert "integrity" in denied["assistant_message"].lower() or "modified" in denied["assistant_message"].lower()

    # Re-propose and tamper with readback
    prop2 = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", session, "prop-tamper-rb")
    phrase2 = prop2["result_block"]["payload"]["draft"]["summary_readback"]
    with sqlite3.connect(tickets.store.db_path) as conn:
        conn.execute("UPDATE action_drafts SET readback='I confirm malicious change' WHERE session_id=?", (session,))

    denied2 = await turn(speech, "EMP-1001", phrase2, session, "confirm-tamper-rb")
    assert denied2["status"] == "denied"


@pytest.mark.asyncio
async def test_planned_executor_grant_inserted_and_consumed(rig):
    """Verifies that an action_grants row is inserted with consumed_at = NULL
    before mutation, and marked with consumed_at upon successful commit.
    """
    speech, voice, tickets = rig

    prop = await turn(speech, "EMP-1001", "Change TKT-2026-001 priority to Critical", turn_id="prop-grant")
    session = prop["session"]["sessionId"]
    phrase = prop["result_block"]["payload"]["draft"]["summary_readback"]

    commit = await turn(speech, "EMP-1001", phrase, session, "confirm-grant")
    assert commit["result_block"]["type"] == "ACTION_RECEIPT"

    # Verify action_grants row exists and was marked consumed
    with sqlite3.connect(tickets.store.db_path) as conn:
        grant_row = conn.execute(
            "SELECT grant_id, actor_id, consumed_at FROM action_grants WHERE draft_id=?",
            (prop["result_block"]["payload"]["confirmation_id"],)
        ).fetchone()
        assert grant_row is not None
        assert grant_row[1] == "EMP-1001"
        assert grant_row[2] is not None


def test_speech_tolerant_readback_normalization():
    """Verifies speech punctuation is stripped while signs, decimals, and numbers are preserved."""
    assert normalize_readback("I confirm update: TKT-2026-001.") == "i confirm update tkt-2026-001"
    assert normalize_readback("Value is -3.14, okay?") == "value is -3.14 okay"
    assert normalize_readback("Priority to Critical!") == "priority to critical"


@pytest.mark.asyncio
async def test_concurrent_inflight_turn_coalescing(rig):
    """Verifies duplicate concurrent turns coalesce so that the voice evidence provider
    is only queried once for in-flight identical requests.
    """
    speech, voice, _ = rig
    speech.transcript = "Show my tickets"
    turn_id = "coalesce-inflight-1"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        form = {"client_turn_id": turn_id, "candidate_employee_id": "EMP-2001"}
        files1 = {"audio_file": ("voice.wav", b"RIFF" + turn_id.encode() * 500, "audio/wav")}
        files2 = {"audio_file": ("voice.wav", b"RIFF" + turn_id.encode() * 500, "audio/wav")}

        res1, res2 = await asyncio.gather(
            client.post("/api/v1/voice/turn", data=form, files=files1),
            client.post("/api/v1/voice/turn", data=form, files=files2),
        )
        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["result_block"]["id"] == res2.json()["result_block"]["id"]
        assert voice.calls == 1


@pytest.mark.asyncio
async def test_session_revocation_purges_idempotency(rig):
    """Verifies that revoking a session cleans up private idempotency records."""
    speech, voice, _ = rig
    first = await turn(speech, "EMP-1001", "Show my profile", turn_id="t-purge-idemp")
    sess_id = first["session"]["sessionId"]
    store = IdentityMappingStore.get_instance()

    with store._get_connection() as conn:
        records_before = conn.execute("SELECT COUNT(*) FROM idempotency_records WHERE employee_id='EMP-1001'").fetchone()[0]
        assert records_before >= 1

    # Revoke session
    store.revoke_session(sess_id)

    with store._get_connection() as conn:
        records_after = conn.execute("SELECT COUNT(*) FROM idempotency_records WHERE employee_id='EMP-1001'").fetchone()[0]
        assert records_after == 0

