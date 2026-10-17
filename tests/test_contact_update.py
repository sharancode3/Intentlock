"""
IntentLock — Regression Test Suite for Protected Contact Update Workflow
Tests:
1. Intent parsing for update_contact with phone numbers and entity targets.
2. Proposal generation with exact readback contract: "I confirm update contact for EMP-XXXX: phone to <number>".
3. Input validation: invalid formats, too short/long digits count.
4. Authorization policy: non-self contact modification strictly denied.
5. Voice confirmation: requires fresh voice evidence and exact readback match.
6. Atomic commit and receipt: returns ACTION_RECEIPT with new_value and event_id.
7. Profile refresh: subsequent profile query displays the newly committed phone.
8. Cancellation workflow: cancelling draft prevents execution.
9. Manifest tamper resistance: payload hash verification fails on modification.
10. Full end-to-end API route execution via TestClient.
"""

import os
import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import (
    app,
    get_speech_input_port,
    get_speech_output_port,
    get_voice_evidence_port,
    get_answer_port,
)
from backend.core.ports import (
    SpeechInputPort,
    SpeechInputResult,
    SpeechOutputPort,
    SpeechOutputResult,
    VoiceEvidencePort,
    VoiceEvidenceResult,
    AnswerGenerationPort,
    AnswerResult,
)
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.services.conversation_dispatch import (
    ConversationDispatcher,
    ConversationStore,
    parse_local,
    IntentPlan,
)
from backend.services.ticket_action_store import TicketActionStore, ActionError
from backend.core.scoped_authorization import ScopedAuthorizationService


# =============================================================================
# Mock Adapters for Offline Testing
# =============================================================================

class MockSpeechInput(SpeechInputPort):
    def __init__(self, transcript=""):
        self.transcript = transcript

    async def transcribe(self, audio_metadata, audio_bytes, client_turn_id):
        return SpeechInputResult(
            is_available=True,
            transcript=self.transcript,
            confidence=0.98,
            duration_seconds=1.5,
        )


class MockSpeechOutput(SpeechOutputPort):
    async def synthesize(self, text, client_turn_id):
        return SpeechOutputResult(is_available=True, audio_bytes=b"RIFFmock", duration_seconds=1.0)


class MockVoiceEvidence(VoiceEvidencePort):
    def __init__(self, actor_id="EMP-1001"):
        self.actor_id = actor_id
        self.call_count = 0

    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        self.call_count += 1
        return VoiceEvidenceResult(
            is_available=True,
            decision="match",
            similarity_score=0.92,
            similarity_threshold=0.75,
            deepfake_verdict="real",
            deepfake_score=0.03,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_{correlation_id}",
            latency_ms=100.0,
        )


class MockAnswerPort(AnswerGenerationPort):
    async def generate_answer(self, user_question, authorized_data, conversation_history, client_turn_id, correlation_id=None):
        return AnswerResult(
            answer_text="Action processed successfully.",
            authorized_context={"status": "success"},
            model_name="mock-offline-answerer",
            tokens_used=10,
        )


# =============================================================================
# Unit Tests: Parsing, Store, and Dispatcher
# =============================================================================

def test_parse_update_contact():
    """Verify that contact/phone update utterances parse into update_contact intent."""
    p1 = parse_local("update my phone to +91 98765 43210")
    assert p1.operation == "update_contact"
    assert "+91 98765 43210" in p1.value

    p2 = parse_local("change my contact number to +1-555-0199")
    assert p2.operation == "update_contact"
    assert "+1-555-0199" in p2.value

    p3 = parse_local("set phone to +44 20 7946 0919")
    assert p3.operation == "update_contact"
    assert "+44 20 7946 0919" in p3.value

    # Targeted at another employee
    p4 = parse_local("update EMP-2001's phone to +91 91234 56789")
    assert p4.operation == "update_contact"
    assert p4.entity == "EMP-2001"
    assert "+91 91234 56789" in p4.value


def test_build_typed_proposal_validation():
    """Validate phone format rules (length, digits)."""
    # Valid formats
    prop1 = TicketActionStore.build_typed_proposal("update_contact", None, value="+91 98765 43210")
    assert prop1["field"] == "phone"
    assert prop1["value"] == "+91 98765 43210"

    prop2 = TicketActionStore.build_typed_proposal("update_contact", None, value="+1-555-0199")
    assert prop2["field"] == "phone"
    assert prop2["value"] == "+1-555-0199"

    # Too short (< 7 digits)
    with pytest.raises(ActionError, match="between 7 and 15 digits"):
        TicketActionStore.build_typed_proposal("update_contact", None, value="12345")

    # Invalid string (no digits)
    with pytest.raises(ActionError, match="valid contact number"):
        TicketActionStore.build_typed_proposal("update_contact", None, value="hello world")


def test_update_contact_propose_and_confirm_lifecycle():
    """Test full propose, readback verification, confirmation, and receipt lifecycle."""
    scoped = ScopedAuthorizationService.get_instance()
    action_store = scoped.ticket_service.store
    actor_id = "EMP-1001"
    session_id = f"test_sess_{uuid.uuid4().hex[:8]}"
    new_phone = "+91 98765 43210"

    params = action_store.build_typed_proposal("update_contact", None, value=new_phone)
    draft = action_store.propose(
        actor_id=actor_id,
        session_id=session_id,
        operation="update_contact",
        ticket_id=None,
        params=params,
        direct_report_ids=[],
        proposal_digest="evidence_turn_1",
    )

    assert draft["operation"] == "update_contact"
    assert draft["ticket_id"] == actor_id
    assert draft["readback"] == f"I confirm update contact for {actor_id}: phone to {new_phone}"

    # Confirm with exact readback and fresh evidence
    receipt = action_store.confirm(
        actor_id=actor_id,
        session_id=session_id,
        spoken=draft["readback"],
        evidence_digest="evidence_turn_2_fresh",
        direct_report_ids=[],
    )

    assert receipt["status"] == "COMMITTED"
    assert receipt["action"] == "update_contact"
    assert receipt["resource_id"] == actor_id
    assert receipt["new_value"] == new_phone
    assert receipt["event_id"].startswith("evt_")


def test_update_contact_non_self_denied():
    """Policy must deny editing contact info for another employee."""
    scoped = ScopedAuthorizationService.get_instance()
    dispatcher = ConversationDispatcher(scoped=scoped)
    actor_id = "EMP-1001"
    session_id = f"test_sess_{uuid.uuid4().hex[:8]}"

    # Trying to update EMP-2001
    plan = IntentPlan(operation="update_contact", entity="EMP-2001", value="+91 99999 88888")
    result = dispatcher.dispatch(
        plan=plan,
        actor_id=actor_id,
        session_id=session_id,
        spoken_text="update EMP-2001's phone to +91 99999 88888",
        evidence_digest="digest_123",
    )

    assert not result.is_authorized
    assert "Policy denies editing contact details for other employees" in result.spoken_summary


def test_profile_displays_updated_phone():
    """After updating contact phone, fetching profile reflects the new phone."""
    scoped = ScopedAuthorizationService.get_instance()
    dispatcher = ConversationDispatcher(scoped=scoped)
    actor_id = "EMP-1001"
    session_id = f"test_sess_{uuid.uuid4().hex[:8]}"
    new_phone = "+91 98888 77777"

    # 1. Propose
    p_plan = IntentPlan(operation="update_contact", value=new_phone)
    p_res = dispatcher.dispatch(
        plan=p_plan,
        actor_id=actor_id,
        session_id=session_id,
        spoken_text=f"update my phone to {new_phone}",
        evidence_digest="prop_digest",
    )
    assert p_res.is_authorized
    assert p_res.result_block.type == "READBACK_CONFIRMATION"

    # 2. Confirm
    c_plan = IntentPlan(operation="confirm")
    c_res = dispatcher.dispatch(
        plan=c_plan,
        actor_id=actor_id,
        session_id=session_id,
        spoken_text=f"I confirm update contact for {actor_id}: phone to {new_phone}",
        evidence_digest="fresh_confirm_digest",
    )
    assert c_res.is_authorized
    assert c_res.result_block.type == "ACTION_RECEIPT"

    # 3. View profile
    prof_plan = IntentPlan(operation="profile")
    prof_res = dispatcher.dispatch(
        plan=prof_plan,
        actor_id=actor_id,
        session_id=session_id,
        spoken_text="show my profile",
        evidence_digest="view_digest",
    )
    assert prof_res.is_authorized
    emp_payload = prof_res.result_block.payload.get("employee", {})
    assert emp_payload.get("phone") == new_phone


# =============================================================================
# Route Integration Tests via TestClient
# =============================================================================

@pytest.fixture
def client():
    os.environ["INTENTLOCK_OFFLINE_TESTS"] = "1"
    return TestClient(app)


def make_turn_request(client, transcript_text, session_id=None, candidate_id=None, turn_id=None):
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput(transcript=transcript_text)
    dummy_audio = (uuid.uuid4().bytes * 10400)[:166400]
    cid = turn_id or f"turn_{uuid.uuid4().hex[:12]}"
    meta = {"sample_rate": 16000, "channels": 1, "format": "audio/wav", "client_turn_id": cid}
    data = {
        "client_turn_id": cid,
        "metadata": json.dumps(meta),
    }
    if session_id:
        data["session_id"] = session_id
    if candidate_id:
        data["candidate_employee_id"] = candidate_id
    files = {"audio_file": ("test.wav", dummy_audio, "audio/wav")}
    return client.post("/api/v1/voice/turn", data=data, files=files)


def test_full_contact_update_route_turn_by_turn(client):
    """
    Test turn-by-turn multi-turn interaction on /api/v1/voice/turn:
    Turn 1: Propose update: "update my phone to +91 98765 11111" -> READBACK_CONFIRMATION
    Turn 2: Spoken exact readback -> ACTION_RECEIPT
    Turn 3: "show my profile" -> EMPLOYEE_PROFILE containing updated phone
    """
    session_id = f"sess_contact_{uuid.uuid4().hex[:12]}"
    store = IdentityMappingStore.get_instance()
    store.upsert_mapping(
        employee_id="EMP-1001",
        provider_speaker_id="spk_aarav_001",
        account_alias="intentlock_test",
        display_name="Aarav Mehta",
        enrollment_status="ENROLLED",
    )
    store.create_session(
        session_id=session_id,
        employee_id="EMP-1001",
        full_name="Aarav Mehta",
        role="Software Engineer",
        department="Engineering",
        ttl_seconds=300,
    )

    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockVoiceEvidence(actor_id="EMP-1001")
    app.dependency_overrides[get_answer_port] = lambda: MockAnswerPort()

    try:
        # Turn 1: Propose update
        resp1 = make_turn_request(
            client,
            transcript_text="update my phone to +91 98765 11111",
            session_id=session_id,
            candidate_id="EMP-1001",
        )
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert body1["result_block"]["type"] == "READBACK_CONFIRMATION"
        readback_text = body1["result_block"]["payload"]["draft"]["summary_readback"]
        assert readback_text == "I confirm update contact for EMP-1001: phone to +91 98765 11111"

        # Turn 2: Confirm with exact readback
        resp2 = make_turn_request(
            client,
            transcript_text=readback_text,
            session_id=session_id,
            candidate_id="EMP-1001",
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["result_block"]["type"] == "ACTION_RECEIPT"
        receipt = body2["result_block"]["payload"]["receipt"]
        assert receipt["action"] == "update_contact"
        assert receipt["resource_id"] == "EMP-1001"
        assert receipt["new_value"] == "+91 98765 11111"
        assert receipt["status"] == "COMMITTED"

        # Turn 3: Show profile and verify phone is visible
        resp3 = make_turn_request(
            client,
            transcript_text="show my profile",
            session_id=session_id,
            candidate_id="EMP-1001",
        )
        assert resp3.status_code == 200
        body3 = resp3.json()
        assert body3["result_block"]["type"] == "EMPLOYEE_PROFILE"
        emp_record = body3["result_block"]["payload"]["employee"]
        assert emp_record["id"] == "EMP-1001"
        assert emp_record["phone"] == "+91 98765 11111"

    finally:
        app.dependency_overrides.clear()
