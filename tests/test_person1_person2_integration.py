"""
IntentLock — Person 1 & Person 2 Comprehensive Integration Test Suite
Validates the complete vertical gateway, semantic planning, identity claim separation,
scoped enterprise queries, authoritative protected actions, and narration grounding.
Strictly offline and isolated.
"""

import io
import json
import os
import re
import pytest
from starlette.testclient import TestClient

from backend.main import (
    app,
    get_speech_input_port,
    get_speech_output_port,
    get_voice_evidence_port,
    get_answer_port,
)
from backend.core.ports import (
    SpeechInputPort,
    SpeechOutputPort,
    VoiceEvidencePort,
    SpeechInputResult,
    SpeechOutputResult,
    VoiceEvidenceResult,
    AnswerGenerationPort,
    AnswerResult,
)
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.adapters.openai_answer_adapter import OpenAIAnswerAdapter
from backend.services.enterprise_dispatcher import enterprise_dispatcher, EnterpriseConversationContext
from backend.services.enterprise_data import enterprise_repo
from backend.services.conversation_dispatch import conversation_store, ConversationDispatcher, IntentPlan
from backend.services.ticket_action_store import TicketActionStore


class MockSpeechInput(SpeechInputPort):
    def __init__(self, transcript: str = "Who am I? My employee ID is EMP-1001"):
        self.mock_transcript = transcript

    async def transcribe(self, audio_metadata, audio_bytes, correlation_id):
        return SpeechInputResult(
            is_available=True,
            transcript=self.mock_transcript,
            confidence=0.98,
            latency_ms=45.0,
            error_message=None,
        )


class MockSpeechOutput(SpeechOutputPort):
    async def synthesize(self, text, correlation_id):
        return SpeechOutputResult(
            is_available=True,
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00",
            audio_format="audio/wav",
            latency_ms=60.0,
            error_message=None,
        )


class MockDualPassVoiceEvidence(VoiceEvidencePort):
    def __init__(self, should_match: bool = True, is_real: bool = True):
        self.should_match = should_match
        self.is_real = is_real

    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        return VoiceEvidenceResult(
            is_available=True,
            decision="match" if self.should_match else "no_match",
            similarity_score=0.94 if self.should_match else 0.22,
            similarity_threshold=0.75,
            deepfake_verdict="real" if self.is_real else "fake",
            deepfake_score=0.06 if self.is_real else 0.95,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_{correlation_id}",
            latency_ms=85.0,
        )


@pytest.fixture
def isolated_mapping_store(tmp_path):
    db_file = str(tmp_path / "test_int_mappings.sqlite3")
    store = IdentityMappingStore(db_path=db_file)
    store.upsert_mapping(
        employee_id="EMP-1001",
        provider_speaker_id="spk_aarav_001",
        account_alias="intentlock_test",
        display_name="Aarav Mehta",
        enrollment_status="ENROLLED",
    )
    store.upsert_mapping(
        employee_id="EMP-2001",
        provider_speaker_id="spk_priya_001",
        account_alias="intentlock_test",
        display_name="Priya Sharma",
        enrollment_status="ENROLLED",
    )
    store.upsert_mapping(
        employee_id="EMP-4002",
        provider_speaker_id="spk_arvind_002",
        account_alias="intentlock_test",
        display_name="Arvind Patel",
        enrollment_status="ENROLLED",
    )
    return store


@pytest.fixture
def integration_client(isolated_mapping_store, monkeypatch):
    monkeypatch.setattr(IdentityMappingStore, "_instance", isolated_mapping_store)

    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence(should_match=True, is_real=True)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def make_test_audio(size: int = 4096) -> bytes:
    return b"RIFF" + b"\x00" * size


# =============================================================================
# SCENARIO 1: Identity Separation and Access Boundaries
# =============================================================================

def test_explicit_spoken_claim_verifies_actor(integration_client):
    """Spoken identity claim 'I am EMP-1001' establishes verified actor."""
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("I am EMP-1001. Show my profile.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-id-01", "candidate_employee_id": "EMP-1001"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["session"]["state"] == "VERIFIED"
    assert body["session"]["actor"]["employeeId"] == "EMP-1001"
    assert body["result_block"]["type"] == "EMPLOYEE_PROFILE"
    assert body["result_block"]["payload"]["employee"]["id"] == "EMP-1001"


def test_target_id_cannot_switch_actor(integration_client):
    """Mentioning a target employee ID in the query must not switch actor identity."""
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Show EMP-2001's tickets.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    # Candidate claim is EMP-1001
    data = {"client_turn_id": "turn-id-02", "candidate_employee_id": "EMP-1001"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    # Verified actor remains EMP-1001
    assert body["session"]["actor"]["employeeId"] == "EMP-1001"


def test_role_only_claim_triggers_clarification(integration_client):
    """Saying 'I am the CTO' without candidate ID asks for employee ID clarification."""
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("I am the CTO. Show executive reports.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-id-03"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "clarification"
    assert body["session"]["state"] == "ANONYMOUS"
    assert "EMP-4002" in body["assistant_message"]


def test_voice_deepfake_denies_private_access(integration_client):
    """Synthetic audio classified as fake produces DENIAL_BANNER and anonymous session."""
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("I am EMP-1001. Show my profile.")
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence(should_match=True, is_real=False)

    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-id-04", "candidate_employee_id": "EMP-1001"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "denied"
    assert body["session"]["state"] == "ANONYMOUS"
    assert body["result_block"]["type"] == "DENIAL_BANNER"
    assert "synthetic" in body["assistant_message"].lower()


# =============================================================================
# SCENARIO 2: Scoped Queries and Hierarchy
# =============================================================================

def test_manager_direct_vs_tree_reports(integration_client):
    """Manager EMP-2001 can query direct reports and full reporting tree."""
    # 1. Direct reports
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Show my direct reports.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-mgr-01", "candidate_employee_id": "EMP-2001"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["result_block"]["type"] == "DATA_TABLE"
    sess_id = body["session"]["sessionId"]

    # 2. Reporting tree
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Show my reporting tree.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-mgr-02", "session_id": sess_id, "candidate_employee_id": "EMP-2001"}

    res2 = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["status"] == "success"
    assert body2["result_block"]["type"] == "ORG_TREE"
    assert body2["result_block"]["payload"]["root_id"] == "EMP-2001"


def test_headcount_authorization_boundary(integration_client):
    """Only executive leadership EMP-4002 can view organization-wide headcount."""
    # Employee EMP-1001 attempt -> Denied
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Show company headcount.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-hc-01", "candidate_employee_id": "EMP-1001"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "denied"
    assert "restricted to executive leadership" in body["assistant_message"]

    # Executive EMP-4002 attempt -> Permitted
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Show company headcount.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-hc-02", "candidate_employee_id": "EMP-4002"}

    res2 = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["status"] == "success"
    assert body2["result_block"]["type"] == "TEAM_METRIC_CHART"
    assert body2["result_block"]["payload"]["title"] == "Company headcount"


def test_unknown_location_asks_clarification(integration_client):
    """Requesting an uncovered location produces clarification without hallucinating zero facilities."""
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Show headcount for Tulum.")
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-loc-01", "candidate_employee_id": "EMP-4002"}

    res = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "clarification"
    assert "Bengaluru" in body["assistant_message"]


# =============================================================================
# SCENARIO 3: Protected Edits and Source of Truth Reconciliation
# =============================================================================

def test_missing_phone_requires_clarification_no_9999999999():
    """Missing phone number returns clarification; never invents 9999999999."""
    ctx = EnterpriseConversationContext()
    ctx.selected_employee_id = "EMP-1001"
    # Utterance without phone number
    res = enterprise_dispatcher.dispatch("Update my contact phone number.", ctx)
    assert res["status"] == "clarification_required"
    assert "9999999999" not in json.dumps(res)


def test_employee_id_digits_not_treated_as_phone():
    """Employee ID digits like EMP-1001 are never extracted as a phone number."""
    ctx = EnterpriseConversationContext()
    res = enterprise_dispatcher.dispatch("Change EMP-1001 phone number.", ctx)
    assert res["status"] == "clarification_required"
    assert "Please provide the phone number" in res["message"]


def test_protected_contact_action_lifecycle(integration_client):
    """End-to-end 2-phase proposal and commit:
    1. Update contact proposed -> READBACK_CONFIRMATION
    2. Confirmation committed -> ACTION_RECEIPT
    3. enterprise_repo updated in-memory
    """
    # Step 1: Propose contact update
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput(
        "Update my work phone to +1-555-0199."
    )
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio()), "audio/wav")}
    data = {"client_turn_id": "turn-edit-01", "candidate_employee_id": "EMP-1001"}

    res1 = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["status"] == "success"
    assert body1["result_block"]["type"] == "READBACK_CONFIRMATION"
    sess_id = body1["session"]["sessionId"]
    readback = body1["result_block"]["payload"]["draft"]["summary_readback"]

    # Step 2: Confirm exact readback with fresh audio recording (anti-replay check)
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput(readback)
    files = {"audio_file": ("speech.wav", io.BytesIO(make_test_audio(size=8192)), "audio/wav")}
    data = {"client_turn_id": "turn-edit-02", "session_id": sess_id, "candidate_employee_id": "EMP-1001"}

    res2 = integration_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["status"] == "success"
    assert body2["result_block"]["type"] == "ACTION_RECEIPT"

    # Step 3: Verify enterprise_repo reflects the update
    emp = enterprise_repo.employees_by_id["EMP-1001"]
    assert emp["identity"]["work_phone"] == "+1-555-0199"


def test_unsupported_role_change_does_not_mutate():
    """Attempting an unsupported promotion does not execute a mutation."""
    ctx = EnterpriseConversationContext()
    res = enterprise_dispatcher.dispatch("Promote Aarav to CEO.", ctx)
    assert res["status"] == "proposal_created"
    assert res["action_proposal"]["authorized"] is False
    # Verify enterprise repo unchanged
    emp = enterprise_repo.employees_by_id["EMP-1001"]
    assert emp["employment"]["designation"] == "Software Engineer"


# =============================================================================
# SCENARIO 4: Narration Grounding and Anti-Hallucination
# =============================================================================

def test_grounding_rejects_positive_count_on_zero_records():
    """Narration claiming records exist when total_count is 0 is rejected."""
    adapter = OpenAIAnswerAdapter(api_key="test-key")
    context = {
        "type": "TICKET_LIST",
        "payload": {
            "total_count": 0,
            "tickets": [],
        }
    }
    is_grounded, reason = adapter.verify_grounding(
        "You have 5 authorized tickets assigned to your team.", context
    )
    assert is_grounded is False
    assert "count mismatch" in reason.lower()


def test_grounding_rejects_pending_described_as_committed():
    """Narration claiming a pending proposal has been committed is rejected."""
    adapter = OpenAIAnswerAdapter(api_key="test-key")
    context = {
        "type": "READBACK_CONFIRMATION",
        "payload": {
            "status": "PENDING",
            "draft": {"action": "update_contact"},
        }
    }
    is_grounded, reason = adapter.verify_grounding(
        "Your work phone has been successfully updated.", context
    )
    assert is_grounded is False
    assert "pending action described as committed" in reason.lower()


def test_grounding_rejects_direct_reports_described_as_company_headcount():
    """Narration claiming direct reports represent the entire company is rejected."""
    adapter = OpenAIAnswerAdapter(api_key="test-key")
    context = {
        "type": "TEAM_METRIC_CHART",
        "title": "Direct reports",
        "payload": {
            "title": "Direct reports",
            "total_count": 4,
        }
    }
    is_grounded, reason = adapter.verify_grounding(
        "The company-wide headcount is 4 employees.", context
    )
    assert is_grounded is False
    assert "scope contradiction" in reason.lower()
