"""
IntentLock — Stage 2 Gateway Integration Test Suite
Validates end-to-end Stage 2 vertical slice:
1. Truthful readiness diagnostics for voice evidence
2. Dual-verification voice turn (/api/v1/voice/turn): MATCH + REAL -> VERIFIED session (90s TTL) + EMPLOYEE_PROFILE
3. Voice turn rejection on synthetic audio (DEEPFAKE) or speaker mismatch -> DENIAL_BANNER
4. Rejection of un-enrolled candidate IDs -> DENIAL_BANNER
5. Session termination endpoint (/api/v1/voice/session/end)
6. Scoped employee profile endpoints (/api/v1/employees/me and /api/v1/employees/{id})
"""

import io
import time
import pytest
from starlette.testclient import TestClient

from backend.main import (
    app,
    get_speech_input_port,
    get_speech_output_port,
    get_voice_evidence_port,
)
from backend.core.ports import (
    SpeechInputPort,
    SpeechOutputPort,
    VoiceEvidencePort,
    SpeechInputResult,
    SpeechOutputResult,
    VoiceEvidenceResult,
)
from backend.adapters.identity_mapping_store import IdentityMappingStore


class MockSpeechInput(SpeechInputPort):
    def __init__(self, transcript: str = "Who am I? My employee ID is EMP-1001"):
        self.mock_transcript = transcript

    async def transcribe(self, audio_metadata, audio_bytes, correlation_id):
        return SpeechInputResult(
            is_available=True,
            transcript=self.mock_transcript,
            confidence=0.98,
            latency_ms=80.0,
            error_message=None,
        )


class MockSpeechOutput(SpeechOutputPort):
    async def synthesize(self, text, correlation_id):
        return SpeechOutputResult(
            is_available=True,
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00",
            audio_format="audio/wav",
            latency_ms=100.0,
            error_message=None,
        )


class MockDualPassVoiceEvidence(VoiceEvidencePort):
    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        return VoiceEvidenceResult(
            is_available=True,
            decision="match",
            similarity_score=0.92,
            similarity_threshold=0.75,
            deepfake_verdict="real",
            deepfake_score=0.08,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_{correlation_id}",
            latency_ms=120.0,
        )


class MockDeepfakeFailVoiceEvidence(VoiceEvidencePort):
    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        return VoiceEvidenceResult(
            is_available=True,
            decision="match",
            similarity_score=0.91,
            similarity_threshold=0.75,
            deepfake_verdict="fake",
            deepfake_score=0.96,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_fake_{correlation_id}",
            latency_ms=115.0,
        )


class MockSpeakerMismatchVoiceEvidence(VoiceEvidencePort):
    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        return VoiceEvidenceResult(
            is_available=True,
            decision="no_match",
            similarity_score=0.31,
            similarity_threshold=0.75,
            deepfake_verdict="real",
            deepfake_score=0.05,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_mismatch_{correlation_id}",
            latency_ms=110.0,
        )


@pytest.fixture
def mock_store(tmp_path):
    """Provide a clean isolated SQLite identity mapping store for tests."""
    db_file = str(tmp_path / "test_gateway_mappings.sqlite3")
    store = IdentityMappingStore(db_path=db_file)
    # Register enrolled test users
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
    return store


@pytest.fixture
def client(mock_store, monkeypatch):
    """Configure TestClient with dependency overrides and mock store."""
    monkeypatch.setattr(IdentityMappingStore, "_instance", mock_store)

    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput()
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def make_dummy_audio(num_bytes: int = 4096) -> bytes:
    # 5 seconds dummy audio bytes
    return b"RIFF" + b"\x00" * num_bytes


def test_readiness_reports_truthfully(client):
    """GET /health/ready truthfully indicates dependencies state."""
    res = client.get("/health/ready")
    assert res.status_code in (200, 503)
    data = res.json()
    assert "status" in data
    assert "components" in data
    assert "voice_evidence" in data["components"]


def test_voice_turn_dual_verification_pass_issues_session(client):
    """A dual-verified turn produces VERIFIED state, 90s session, and sanitized profile."""
    audio = make_dummy_audio()
    files = {"audio_file": ("speech.wav", io.BytesIO(audio), "audio/wav")}
    data = {
        "client_turn_id": "turn-test-pass-001",
        "candidate_employee_id": "EMP-1001",
    }

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()

    assert body["status"] == "success"
    assert body["session"]["state"] == "VERIFIED"
    assert body["session"]["sessionId"] is not None
    assert body["session"]["actor"]["employeeId"] == "EMP-1001"
    assert body["session"]["actor"]["fullName"] == "Aarav Mehta"
    assert body["session"]["actor"]["expiresInSeconds"] <= 90

    # Trust evidence checks
    evidence = body["trust_evidence"]
    assert evidence is not None
    assert evidence["is_dual_verified"] is True
    assert evidence["speaker_decision"] == "match"
    assert evidence["authenticity_verdict"] == "real"
    assert evidence["similarity_score"] >= 0.75
    assert evidence["deepfake_score"] < 0.50

    # Generic result block checks
    block = body["result_block"]
    assert block is not None
    assert block["type"] == "EMPLOYEE_PROFILE"
    assert block["payload"]["employee"]["id"] == "EMP-1001"
    assert "Aarav Mehta" in body["spoken_summary"]
    assert body["speech_audio"] is not None


def test_voice_turn_deepfake_rejection(client):
    """When deepfake detection fails, turn is denied and no private profile is returned."""
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDeepfakeFailVoiceEvidence()

    audio = make_dummy_audio()
    files = {"audio_file": ("speech.wav", io.BytesIO(audio), "audio/wav")}
    data = {
        "client_turn_id": "turn-test-fake-001",
        "candidate_employee_id": "EMP-1001",
    }

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()

    assert body["status"] == "denied"
    assert body["session"]["state"] == "ANONYMOUS"
    assert body["session"]["sessionId"] is None
    assert body["trust_evidence"]["is_dual_verified"] is False
    assert body["trust_evidence"]["authenticity_verdict"] == "fake"

    # Denial banner returned, no employee object
    assert body["result_block"]["type"] == "DENIAL_BANNER"
    assert "synthetic audio" in body["result_block"]["payload"]["reason"].lower()
    assert "employee" not in body["result_block"]["payload"]


def test_voice_turn_speaker_mismatch_rejection(client):
    """When speaker does not match candidate, turn is denied with denial banner."""
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockSpeakerMismatchVoiceEvidence()

    audio = make_dummy_audio()
    files = {"audio_file": ("speech.wav", io.BytesIO(audio), "audio/wav")}
    data = {
        "client_turn_id": "turn-test-mismatch-001",
        "candidate_employee_id": "EMP-1001",
    }

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()

    assert body["status"] == "denied"
    assert body["trust_evidence"]["is_dual_verified"] is False
    assert body["trust_evidence"]["speaker_decision"] == "no_match"
    assert body["result_block"]["type"] == "DENIAL_BANNER"


def test_voice_turn_unenrolled_candidate(client):
    """An employee ID with no enrollment mapping returns unregistered denial."""
    audio = make_dummy_audio()
    files = {"audio_file": ("speech.wav", io.BytesIO(audio), "audio/wav")}
    data = {
        "client_turn_id": "turn-test-unregistered-001",
        "candidate_employee_id": "EMP-9999",
    }

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200
    body = res.json()

    assert body["status"] in ("unverified", "denied")
    assert body["session"]["state"] == "ANONYMOUS"
    assert body["result_block"]["type"] == "DENIAL_BANNER"
    assert "not enrolled" in body["result_block"]["payload"]["reason"].lower()


def test_session_end_lifecycle(client):
    """Active session can be terminated and immediately rejected thereafter."""
    # 1. Authenticate to get session
    audio = make_dummy_audio()
    files = {"audio_file": ("speech.wav", io.BytesIO(audio), "audio/wav")}
    res = client.post(
        "/api/v1/voice/turn",
        files=files,
        data={"client_turn_id": "turn-sess-term-001", "candidate_employee_id": "EMP-1001"},
    )
    token = res.json()["session"]["sessionId"]
    assert token is not None

    # 2. Access /api/v1/employees/me with session
    res_me = client.get("/api/v1/employees/me", headers={"X-Session-Token": token})
    assert res_me.status_code == 200
    assert res_me.json()["employee"]["id"] == "EMP-1001"

    # 3. Terminate session
    res_term = client.post("/api/v1/voice/session/end", headers={"X-Session-Token": token})
    assert res_term.status_code == 200
    assert res_term.json()["status"] == "session_terminated"

    # 4. Subsequent access is rejected with 401
    res_me_revoked = client.get("/api/v1/employees/me", headers={"X-Session-Token": token})
    assert res_me_revoked.status_code == 401


def test_scoped_employee_endpoints(client):
    """Authorized manager can view direct report, but colleague access is forbidden."""
    # 1. Establish session for EMP-1001 (Aarav, L1)
    audio = make_dummy_audio()
    files = {"audio_file": ("speech.wav", io.BytesIO(audio), "audio/wav")}
    res_aarav = client.post(
        "/api/v1/voice/turn",
        files=files,
        data={"client_turn_id": "turn-aarav-auth", "candidate_employee_id": "EMP-1001"},
    )
    aarav_token = res_aarav.json()["session"]["sessionId"]

    # Aarav trying to view peer EMP-1002 (Sneha Rao) -> 403 Forbidden
    res_forbidden = client.get("/api/v1/employees/EMP-1002", headers={"X-Session-Token": aarav_token})
    assert res_forbidden.status_code == 403
    assert res_forbidden.json()["type"] == "DENIAL_BANNER"

    # 2. Establish session for EMP-2001 (Priya Sharma, Manager)
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("My ID is EMP-2001")
    res_priya = client.post(
        "/api/v1/voice/turn",
        files=files,
        data={"client_turn_id": "turn-priya-auth", "candidate_employee_id": "EMP-2001"},
    )
    priya_token = res_priya.json()["session"]["sessionId"]

    # Priya viewing direct report EMP-1001 -> 200 OK
    res_manager = client.get("/api/v1/employees/EMP-1001", headers={"X-Session-Token": priya_token})
    assert res_manager.status_code == 200
    assert res_manager.json()["employee"]["id"] == "EMP-1001"
    assert res_manager.json()["employee"]["name"] == "Aarav Mehta"
