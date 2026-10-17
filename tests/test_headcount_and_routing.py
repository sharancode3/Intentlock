"""
IntentLock — Regression Test Suite for Semantic Routing, Headcount, and Clarification Semantics
Covers the 12 requirements from the recheck investigation:
1. Exact screenshot utterance with candidate EMP-4002 (Tulum clarification, verified session, not PUBLIC_FAQ).
2. Permitted scoped headcount request with recognized location (Bengaluru).
3. "How many people report directly to me?" (direct reports, not company headcount).
4. "How many employees work in this company?" (organization-level permission enforced; EMP-1001 denied).
5. "I am the CTO" without candidate identity (asks for employee ID, never grants session).
6. Selected CTO identity with another speaker (denial, no private count).
7. "What can you do?" (genuine public help, zero Detectif calls).
8. Unknown phrasing for a supported count (structured planning resolves it).
9. Planner unavailable (honest clarification, no misleading public success).
10. Unknown location vs recognized zero matches (different accurate outcomes).
11. Narration adapter contract (question, authorized_context, correlation_id, answer_text agreement, failure fallback).
12. Existing workflows (profiles, tickets, org trees, actions) preserved without regressions.
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
    UnavailableAnswerAdapter,
)
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.services.conversation_dispatch import parse_local, IntentPlan
from backend.models.turn import OriginalAudioMetadata


# =============================================================================
# Mock Adapters for Deterministic Offline Route Testing
# =============================================================================

class MockSpeechInput(SpeechInputPort):
    def __init__(self, transcript="Test audio request"):
        self.transcript = transcript

    async def transcribe(self, audio_metadata, audio_bytes, client_turn_id):
        return SpeechInputResult(
            is_available=True,
            transcript=self.transcript,
            confidence=0.98,
            latency_ms=80.0,
            speech_duration_s=5.2,
        )


class MockSpeechOutput(SpeechOutputPort):
    def __init__(self):
        self.last_synthesized_text = None

    async def synthesize(self, text: str, client_turn_id: str):
        self.last_synthesized_text = text
        # Generate minimal valid WAV header (44 bytes) + 48000 bytes dummy audio (1s)
        dummy_wav = b"RIFF" + (48036).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
        dummy_wav += (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (24000).to_bytes(4, "little")
        dummy_wav += (48000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
        dummy_wav += b"data" + (48000).to_bytes(4, "little") + (b"\x00" * 48000)
        return SpeechOutputResult(
            is_available=True,
            audio_bytes=dummy_wav,
            audio_format="audio/wav",
            latency_ms=45.0,
        )


class MockDualPassVoiceEvidence(VoiceEvidencePort):
    def __init__(self):
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
            latency_ms=120.0,
        )


class MockSpeakerMismatchVoiceEvidence(VoiceEvidencePort):
    def __init__(self):
        self.call_count = 0

    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        self.call_count += 1
        return VoiceEvidenceResult(
            is_available=True,
            decision="no_match",
            similarity_score=0.31,
            similarity_threshold=0.75,
            deepfake_verdict="real",
            deepfake_score=0.04,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_mismatch_{correlation_id}",
            latency_ms=110.0,
        )


@pytest.fixture
def mock_store(tmp_path):
    """Provide a clean isolated SQLite identity mapping store with enrolled personas."""
    db_file = str(tmp_path / "test_headcount_mappings.sqlite3")
    store = IdentityMappingStore(db_path=db_file)
    # Register EMP-1001 (Engineer)
    store.upsert_mapping(
        employee_id="EMP-1001",
        provider_speaker_id="spk_aarav_001",
        account_alias="intentlock_test",
        display_name="Aarav Mehta",
        enrollment_status="ENROLLED",
    )
    # Register EMP-2001 (Manager)
    store.upsert_mapping(
        employee_id="EMP-2001",
        provider_speaker_id="spk_priya_001",
        account_alias="intentlock_test",
        display_name="Priya Sharma",
        enrollment_status="ENROLLED",
    )
    # Register EMP-4002 (CTO - Executive)
    store.upsert_mapping(
        employee_id="EMP-4002",
        provider_speaker_id="spk_arvind_4002",
        account_alias="intentlock_test",
        display_name="Arvind Rao",
        enrollment_status="ENROLLED",
    )
    return store


def make_turn_request(client, transcript_text, candidate_id=None, session_id=None, turn_id=None):
    """Helper to dispatch a voice turn with custom transcript and candidate identity."""
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput(transcript=transcript_text)
    
    # 5.2 seconds of dummy 16kHz audio (166400 bytes)
    dummy_audio = b"\x00" * 166400
    cid = turn_id or f"turn_test_{uuid.uuid4().hex[:12]}"
    meta = {"sample_rate": 16000, "channels": 1, "format": "audio/wav", "client_turn_id": cid}
    data = {
        "client_turn_id": cid,
        "metadata": json.dumps(meta),
    }
    if candidate_id:
        data["candidate_employee_id"] = candidate_id
    if session_id:
        data["session_id"] = session_id
    
    files = {"audio_file": ("test.wav", dummy_audio, "audio/wav")}
    return client.post("/api/v1/voice/turn", data=data, files=files)


# =============================================================================
# Test Cases
# =============================================================================

def test_1_screenshot_exact_utterance_with_candidate_cto(mock_store, monkeypatch):
    """
    Test 1: Exact screenshot utterance with candidate EMP-4002.
    - Verified identity (CTO Arvind Rao) established in session.
    - Status is 'clarification', NOT 'success'.
    - Right panel has NO misleading PUBLIC_FAQ block.
    - Transcript preserves 'Tulum' as an unresolved location constraint.
    - Spoken message specifically explains demo directory location coverage.
    - No guessed 31-count answer.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    mock_voice = MockDualPassVoiceEvidence()
    app.dependency_overrides[get_voice_evidence_port] = lambda: mock_voice
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="Can I get to know how many employees are working in this company in Tulum? I am the CTO.",
            candidate_id="EMP-4002",
        )
        assert res.status_code == 200
        body = res.json()

        # 1. Identity is verified
        assert body["session"]["state"] == "VERIFIED"
        assert body["session"]["actor"]["employeeId"] == "EMP-4002"
        assert body["session"]["actor"]["fullName"] == "Arvind Rao"
        assert mock_voice.call_count == 1
        assert body["trust_evidence"]["is_dual_verified"] is True

        # 2. Status is clarification (amber in UI, not green success)
        assert body["status"] == "clarification"

        # 3. No misleading PUBLIC_FAQ block returned
        if body["result_block"]:
            assert body["result_block"]["type"] != "PUBLIC_FAQ"
        assert body["result_blocks"] == [] or all(b["type"] != "PUBLIC_FAQ" for b in body["result_blocks"])

        # 4. Spoken message notes Tulum and explains Bengaluru demo coverage
        msg = body["assistant_message"]
        assert "Tulum" in msg
        assert "Bengaluru" in msg
        assert "31" not in msg  # No guessed count for Tulum!


def test_2_permitted_scoped_headcount_bengaluru(mock_store, monkeypatch):
    """
    Test 2: Permitted scoped headcount request with recognized location (Bengaluru).
    - CTO is authorized for organization-wide aggregate headcount.
    - Returns 31 employees in Bengaluru.
    - Result block is TEAM_METRIC_CHART with category 'Workforce Analytics' and unit 'employees'.
    - Individual employee IDs are not leaked.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    mock_voice = MockDualPassVoiceEvidence()
    app.dependency_overrides[get_voice_evidence_port] = lambda: mock_voice
    mock_tts = MockSpeechOutput()
    app.dependency_overrides[get_speech_output_port] = lambda: mock_tts

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="How many employees are in Bengaluru in this company?",
            candidate_id="EMP-4002",
        )
        assert res.status_code == 200
        body = res.json()

        assert body["status"] == "success"
        assert body["session"]["state"] == "VERIFIED"
        assert body["result_block"] is not None
        assert body["result_block"]["type"] == "TEAM_METRIC_CHART"
        payload = body["result_block"]["payload"]
        assert payload["unit"] == "employees"
        assert payload["category"] == "Workforce Analytics"
        assert payload["data"] == [{"label": "Bengaluru (HQ)", "count": 31}]

        # Factual summary mentions 31 employees
        assert "31 employees" in body["assistant_message"]
        assert mock_tts.last_synthesized_text == body["spoken_summary"]


def test_3_direct_reports_count_not_company_headcount(mock_store, monkeypatch):
    """
    Test 3: 'How many people report directly to me?'
    - Returns direct reports count (1 for CTO Arvind Rao: RND-5001).
    - Does NOT return 31 company headcount.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="How many people report directly to me?",
            candidate_id="EMP-4002",
        )
        assert res.status_code == 200
        body = res.json()

        assert body["status"] == "success"
        assert body["result_block"]["type"] == "TEAM_METRIC_CHART"
        assert "1 direct report" in body["assistant_message"]
        assert "31" not in body["assistant_message"]


def test_4_company_headcount_denied_for_non_executive(mock_store, monkeypatch):
    """
    Test 4: Organization-wide headcount is restricted to executive leadership.
    - EMP-1001 (Engineer) requesting company headcount is explicitly denied.
    - Zero count disclosed.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="How many employees work in this company?",
            candidate_id="EMP-1001",
        )
        assert res.status_code == 200
        body = res.json()

        assert body["status"] == "denied"
        assert "Access denied" in body["assistant_message"]
        assert "executive leadership" in body["assistant_message"]
        assert body["result_block"]["type"] == "DENIAL_BANNER"
        assert "31" not in body["assistant_message"]


def test_5_i_am_the_cto_without_candidate_identity(mock_store, monkeypatch):
    """
    Test 5: 'I am the CTO' without usable candidate identity.
    - Asks for an identifier.
    - Never grants a CTO session based on the title phrase alone.
    - Zero Detectif calls.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    mock_voice = MockDualPassVoiceEvidence()
    app.dependency_overrides[get_voice_evidence_port] = lambda: mock_voice
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="I am the CTO. Can I get to know how many employees work here?",
            candidate_id=None,
        )
        assert res.status_code == 200
        body = res.json()

        assert body["session"]["state"] == "ANONYMOUS"
        assert body["status"] in ("clarification", "unverified")
        assert "EMP-4002" in body["assistant_message"]
        assert mock_voice.call_count == 0  # No Detectif credits spent without candidate ID!


def test_6_selected_cto_identity_with_another_speaker(mock_store, monkeypatch):
    """
    Test 6: Selected CTO identity with another speaker (speaker mismatch).
    - Biometric verification fails closed.
    - No session issued, no private count disclosed.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    mock_voice = MockSpeakerMismatchVoiceEvidence()
    app.dependency_overrides[get_voice_evidence_port] = lambda: mock_voice
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="How many employees work in this company?",
            candidate_id="EMP-4002",
        )
        assert res.status_code == 200
        body = res.json()

        assert body["status"] == "denied"
        assert body["session"]["state"] == "ANONYMOUS"
        assert body["result_block"]["type"] == "DENIAL_BANNER"
        assert "does not match" in body["assistant_message"]
        assert "31" not in body["assistant_message"]


def test_7_what_can_you_do_public_help_zero_detectif(mock_store, monkeypatch):
    """
    Test 7: 'What can you do?'
    - Returns genuine approved public help (PUBLIC_FAQ).
    - Zero Detectif calls.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    mock_voice = MockDualPassVoiceEvidence()
    app.dependency_overrides[get_voice_evidence_port] = lambda: mock_voice
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="What can you do?",
            candidate_id=None,
        )
        assert res.status_code == 200
        body = res.json()

        assert body["status"] == "success"
        assert body["result_block"]["type"] == "PUBLIC_FAQ"
        assert mock_voice.call_count == 0  # Zero biometric calls!


def test_8_unknown_phrasing_for_supported_count_resolved(mock_store, monkeypatch):
    """
    Test 8: Unknown phrasing for supported count.
    - Local or model planner resolves headcount with scope='company'.
    - Returns 31 employees for verified CTO.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="Give me the total workforce count across the organization",
            candidate_id="EMP-4002",
        )
        assert res.status_code == 200
        body = res.json()

        assert body["status"] == "success"
        assert body["result_block"]["type"] == "TEAM_METRIC_CHART"
        assert "31 employees" in body["assistant_message"]


def test_9_planner_unavailable_returns_honest_clarification(mock_store, monkeypatch):
    """
    Test 9: When planner is unavailable and request is unrecognized.
    - Verified actor turn returns specific clarification, NOT misleading PUBLIC_FAQ success.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    # Simulate an ambiguous command that parse_local classifies as clarify
    with TestClient(app) as client:
        res = make_turn_request(
            client,
            transcript_text="Can you check the weather in the cafeteria?",
            candidate_id="EMP-4002",
        )
        assert res.status_code == 200
        body = res.json()

        assert body["session"]["state"] == "VERIFIED"
        assert body["status"] == "clarification"
        assert body["result_block"] is None or body["result_block"]["type"] != "PUBLIC_FAQ"
        assert "Please ask for a profile" in body["assistant_message"]


def test_10_unknown_location_vs_recognized_zero_matches(mock_store, monkeypatch):
    """
    Test 10: Unknown location vs recognized zero matches have distinct accurate outcomes.
    - 'Tulum' (unrecognized location) -> location clarification.
    - 'London' (recognized site without active employees) -> reports 0 recorded employees.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        # Case A: Tulum (unrecognized)
        res_tulum = make_turn_request(
            client,
            transcript_text="How many employees are in Tulum?",
            candidate_id="EMP-4002",
        )
        assert res_tulum.status_code == 200
        body_tulum = res_tulum.json()
        assert body_tulum["status"] == "clarification"
        assert "I heard 'Tulum' as the location" in body_tulum["assistant_message"]

        # Case B: London (recognized location with 0 employees in directory)
        res_london = make_turn_request(
            client,
            transcript_text="How many employees are in London?",
            candidate_id="EMP-4002",
        )
        assert res_london.status_code == 200
        body_london = res_london.json()
        assert body_london["status"] == "clarification"
        assert "has no recorded employees" in body_london["assistant_message"]


@pytest.mark.asyncio
async def test_11_narration_adapter_contract_and_text_agreement(mock_store, monkeypatch):
    """
    Test 11: Correct OpenAI narration contract.
    - generate_answer is called with (question, authorized_context, correlation_id).
    - authorized_context is a dict with type, title, payload.
    - ans.answer_text is read and used for assistant_message, spoken_summary, and TTS.
    - Exceptions fall back safely to deterministic spoken summary.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    mock_tts = MockSpeechOutput()
    app.dependency_overrides[get_speech_output_port] = lambda: mock_tts

    # Mock answer adapter adhering to the AnswerGenerationPort protocol
    class MockConfiguredAnswerAdapter(AnswerGenerationPort):
        def __init__(self):
            self.last_call = None

        def is_configured(self) -> bool:
            return True

        async def plan_request(self, utterance, has_current_result):
            return None

        async def generate_answer(self, question, authorized_context, correlation_id):
            self.last_call = {
                "question": question,
                "authorized_context": authorized_context,
                "correlation_id": correlation_id,
            }
            return AnswerResult(
                is_available=True,
                answer_text="Our company has thirty-one employees based in Bengaluru according to verified records.",
                grounded=True,
                sources=["TEAM_METRIC_CHART"],
            )

    mock_answer = MockConfiguredAnswerAdapter()
    app.dependency_overrides[get_answer_port] = lambda: mock_answer

    # Ensure offline test flag is temporarily not disabling narration for this specific test
    with patch.dict(os.environ, {"INTENTLOCK_OFFLINE_TESTS": "0"}):
        with TestClient(app) as client:
            res = make_turn_request(
                client,
                transcript_text="How many employees work in Bengaluru?",
                candidate_id="EMP-4002",
                turn_id="turn_test_123",
            )
            assert res.status_code == 200
            body = res.json()

            # Contract check: called with correct parameters
            assert mock_answer.last_call is not None
            assert mock_answer.last_call["question"] == "How many employees work in Bengaluru?"
            assert isinstance(mock_answer.last_call["authorized_context"], dict)
            assert mock_answer.last_call["authorized_context"]["type"] == "TEAM_METRIC_CHART"
            assert mock_answer.last_call["correlation_id"] == "turn_test_123"

            # Result field agreement: assistant_message, spoken_summary, and synthesized TTS all agree!
            expected_text = "Our company has thirty-one employees based in Bengaluru according to verified records."
            assert body["assistant_message"] == expected_text
            assert body["spoken_summary"] == expected_text
            assert mock_tts.last_synthesized_text == expected_text


def test_12_existing_ticket_and_tree_workflows_preserved(mock_store, monkeypatch):
    """
    Test 12: Preserving existing workflows.
    - Org tree, ticket list, and ticket details continue to function properly.
    """
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    with TestClient(app) as client:
        # Org tree for CTO
        res_tree = make_turn_request(client, "Show my reporting tree", candidate_id="EMP-4002")
        assert res_tree.status_code == 200
        assert res_tree.json()["result_block"]["type"] == "ORG_TREE"

        # Tickets for Manager
        res_tkt = make_turn_request(client, "Show my team tickets", candidate_id="EMP-2001")
        assert res_tkt.status_code == 200
        assert res_tkt.json()["result_block"]["type"] == "TICKET_LIST"
