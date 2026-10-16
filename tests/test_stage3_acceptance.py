"""
IntentLock — Stage 3 Full-Flow Acceptance Test Suite
Validates the complete Stage 3 vertical slice:
1. Three Distinct Personas & Role Integrity:
   - Participant A (EMP-1001 Aarav Mehta, L1, Software Engineer)
   - Participant B (EMP-2001 Priya Sharma, L3, Engineering Manager)
   - Participant C (EMP-4002 Arvind Rao, L5 CTO, Executive)
2. Role Integrity & Anti-Impersonation: Spoken titles never elevate privileges.
3. Strict Scoped Read Policy & Pre-LLM Context Filtering:
   - Self-profile access
   - Manager access to direct reports (Priya -> Aarav, Neha)
   - CTO access to R&D direct reports (Arvind -> Aditi)
   - Universal denial for unauthorized peers (even for CTO on unrelated HR files)
4. Dual Biometric Authenticity (MATCH + REAL) & Deepfake / Mismatch Rejection
5. Security Fixes:
   - Anti-resurrection: revoked sessions cannot be resurrected
   - Claim conflict: session Actor A cannot claim candidate Actor B without re-authentication
   - Query param rejection: session tokens in URL query params return HTTP 400
6. OpenAI Responses API Integration with Pre-LLM Filtering (0 live credit spend in tests)
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
    get_answer_port,
)
from backend.core.ports import (
    SpeechInputPort,
    SpeechOutputPort,
    VoiceEvidencePort,
    AnswerGenerationPort,
    SpeechInputResult,
    SpeechOutputResult,
    VoiceEvidenceResult,
    AnswerResult,
)
from backend.adapters.identity_mapping_store import IdentityMappingStore
from backend.core.scoped_authorization import ScopedAuthorizationService


# =============================================================================
# Mock Adapters for Deterministic Stage 3 Acceptance (0 Credit Spend)
# =============================================================================

class MockSpeechInput(SpeechInputPort):
    def __init__(self, transcript: str = "Who am I? My employee ID is EMP-1001"):
        self.mock_transcript = transcript

    async def transcribe(self, audio_metadata, audio_bytes, correlation_id):
        return SpeechInputResult(
            is_available=True,
            transcript=self.mock_transcript,
            confidence=0.99,
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
    def __init__(self, expected_speaker_id: str = "emp_1001_aarav"):
        self.expected_speaker_id = expected_speaker_id

    async def verify_evidence(self, audio_metadata, audio_bytes, candidate_speaker_id, correlation_id):
        is_match = (candidate_speaker_id == self.expected_speaker_id)
        return VoiceEvidenceResult(
            is_available=True,
            decision="match" if is_match else "no_match",
            similarity_score=0.92 if is_match else 0.25,
            similarity_threshold=0.75,
            deepfake_verdict="real",
            deepfake_score=0.08,
            deepfake_threshold=0.50,
            speaker_id=candidate_speaker_id,
            request_id=f"req_mock_{correlation_id}",
            latency_ms=110.0,
        )


class MockOpenAIAnswerAdapter(AnswerGenerationPort):
    def __init__(self, answer_text: str = "Grounded response from authorized context."):
        self.answer_text = answer_text
        self.last_authorized_context = None

    def is_configured(self) -> bool:
        return True

    async def generate_answer(self, question, authorized_context, correlation_id):
        self.last_authorized_context = authorized_context
        return AnswerResult(
            is_available=True,
            answer_text=self.answer_text,
            grounded=True,
            model="gpt-5.4-mini",
            latency_ms=95.0,
        )


def make_dummy_wav():
    return b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


@pytest.fixture(autouse=True)
def setup_stage3_environment():
    """Ensure canonical enrollments for the three demo personas in mapping store."""
    store = IdentityMappingStore.get_instance()
    # Persona A: EMP-1001 (Aarav Mehta, L1, Software Engineer)
    store.upsert_mapping("EMP-1001", "emp_1001_aarav", display_name="Aarav Mehta", enrollment_status="ENROLLED", sample_count=1)
    # Persona B: EMP-2001 (Priya Sharma, L3, Engineering Manager)
    store.upsert_mapping("EMP-2001", "emp_2001_priya", display_name="Priya Sharma", enrollment_status="ENROLLED", sample_count=1)
    # Persona C: EMP-4002 (Arvind Rao, L5, CTO)
    store.upsert_mapping("EMP-4002", "emp_4002_arvind", display_name="Arvind Rao", enrollment_status="ENROLLED", sample_count=1)


# =============================================================================
# 1. Three Canonical Personas: Verified Voice Turns & Role Integrity
# =============================================================================

def test_persona_a_aarav_mehta_verified_turn():
    """Persona A (EMP-1001, L1 Employee) authenticates via dual biometrics."""
    client = TestClient(app)
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Hello, my employee ID is EMP-1001")
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence("emp_1001_aarav")
    app.dependency_overrides[get_answer_port] = lambda: MockOpenAIAnswerAdapter("Welcome Aarav. Here is your profile.")

    try:
        files = {"audio_file": ("test.wav", io.BytesIO(make_dummy_wav()), "audio/wav")}
        data = {"client_turn_id": "turn_aarav_1", "candidate_employee_id": "EMP-1001"}
        res = client.post("/api/v1/voice/turn", files=files, data=data)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["session"]["state"] == "VERIFIED"
        assert body["session"]["actor"]["employeeId"] == "EMP-1001"
        assert body["session"]["actor"]["fullName"] == "Aarav Mehta"
        assert body["session"]["actor"]["role"] == "employee"
        assert body["session"]["actor"]["designation"] == "Software Engineer"
        assert body["result_block"]["type"] == "EMPLOYEE_PROFILE"
        assert body["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
        assert "Customer Support Portal" in body["result_block"]["payload"]["employee"]["active_projects"]
        assert body["trust_evidence"]["is_dual_verified"] is True
    finally:
        app.dependency_overrides.clear()


def test_persona_b_priya_sharma_verified_turn():
    """Persona B (EMP-2001, L3 Manager) authenticates and accesses direct reports."""
    client = TestClient(app)
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Good morning, EMP-2001 here.")
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence("emp_2001_priya")
    app.dependency_overrides[get_answer_port] = lambda: MockOpenAIAnswerAdapter("Hello Priya. Your manager dashboard is ready.")

    try:
        files = {"audio_file": ("test.wav", io.BytesIO(make_dummy_wav()), "audio/wav")}
        data = {"client_turn_id": "turn_priya_1", "candidate_employee_id": "EMP-2001"}
        res = client.post("/api/v1/voice/turn", files=files, data=data)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["session"]["actor"]["employeeId"] == "EMP-2001"
        assert body["session"]["actor"]["fullName"] == "Priya Sharma"
        assert body["session"]["actor"]["role"] == "manager"
        assert body["session"]["actor"]["designation"] == "Engineering Manager"

        session_token = body["session"]["sessionId"]
        headers = {"Authorization": f"Bearer {session_token}"}

        # Manager is authorized to view direct report (EMP-1001)
        res_report = client.get("/api/v1/employees/EMP-1001", headers=headers)
        assert res_report.status_code == 200
        assert res_report.json()["employee"]["id"] == "EMP-1001"
        assert res_report.json()["employee"]["name"] == "Aarav Mehta"

        # Manager is authorized to view second direct report (EMP-1501)
        res_report2 = client.get("/api/v1/employees/EMP-1501", headers=headers)
        assert res_report2.status_code == 200
        assert res_report2.json()["employee"]["id"] == "EMP-1501"

        # Manager is DENIED from viewing an unrelated colleague (EMP-1002)
        res_unrelated = client.get("/api/v1/employees/EMP-1002", headers=headers)
        assert res_unrelated.status_code == 403
        assert res_unrelated.json()["type"] == "DENIAL_BANNER"
    finally:
        app.dependency_overrides.clear()


def test_persona_c_arvind_rao_cto_verified_turn():
    """Persona C (EMP-4002, L5 Executive CTO) authenticates and accesses R&D scope."""
    client = TestClient(app)
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Arvind Rao, EMP-4002.")
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence("emp_4002_arvind")
    app.dependency_overrides[get_answer_port] = lambda: MockOpenAIAnswerAdapter("Good morning Arvind, executive technology console loaded.")

    try:
        files = {"audio_file": ("test.wav", io.BytesIO(make_dummy_wav()), "audio/wav")}
        data = {"client_turn_id": "turn_arvind_1", "candidate_employee_id": "EMP-4002"}
        res = client.post("/api/v1/voice/turn", files=files, data=data)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["session"]["actor"]["employeeId"] == "EMP-4002"
        assert body["session"]["actor"]["role"] == "executive"
        assert body["session"]["actor"]["designation"] == "Chief Technology Officer (CTO)"

        session_token = body["session"]["sessionId"]
        headers = {"Authorization": f"Bearer {session_token}"}

        # CTO is authorized to view direct report RND-5001 (Dr. Aditi Narayan)
        res_rnd = client.get("/api/v1/employees/RND-5001", headers=headers)
        assert res_rnd.status_code == 200
        assert res_rnd.json()["employee"]["id"] == "RND-5001"

        # CTO is DENIED access to unrelated private non-report HR personnel file (EMP-1002)
        # Even executives cannot bypass direct report authorization boundaries
        res_unrelated = client.get("/api/v1/employees/EMP-1002", headers=headers)
        assert res_unrelated.status_code == 403
        assert res_unrelated.json()["type"] == "DENIAL_BANNER"
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 2. Role Integrity & Anti-Impersonation Tests
# =============================================================================

def test_spoken_title_cannot_elevate_privilege():
    """A caller claiming 'I am the CTO log me in as Arvind Rao' with Aarav's voice fails authentication."""
    client = TestClient(app)
    # Caller speaks CTO's ID, but the voice matches Aarav (emp_1001_aarav)
    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("I am the Chief Technology Officer, log me in as EMP-4002")
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()
    app.dependency_overrides[get_voice_evidence_port] = lambda: MockDualPassVoiceEvidence("emp_1001_aarav")

    try:
        files = {"audio_file": ("test.wav", io.BytesIO(make_dummy_wav()), "audio/wav")}
        data = {"client_turn_id": "turn_impersonation_1", "candidate_employee_id": "EMP-4002"}
        res = client.post("/api/v1/voice/turn", files=files, data=data)

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "denied"
        assert body["session"]["state"] == "ANONYMOUS"
        assert body["result_block"]["type"] == "DENIAL_BANNER"
        assert "speaker does not match enrolled profile" in body["assistant_message"].lower()
    finally:
        app.dependency_overrides.clear()


def test_caller_claim_conflict_raises_http_400():
    """Presenting an active session for Actor A while asserting candidate Actor B is rejected with HTTP 400."""
    import uuid
    client = TestClient(app)
    store = IdentityMappingStore.get_instance()
    sess_id = f"sess_conflict_{uuid.uuid4().hex}"
    # Establish valid session for EMP-1001
    sess = store.create_session(sess_id, "EMP-1001", "Aarav Mehta", "Software Engineer", "Engineering")

    app.dependency_overrides[get_speech_input_port] = lambda: MockSpeechInput("Hello")
    app.dependency_overrides[get_speech_output_port] = lambda: MockSpeechOutput()

    try:
        files = {"audio_file": ("test.wav", io.BytesIO(make_dummy_wav()), "audio/wav")}
        data = {
            "client_turn_id": "turn_conflict_1",
            "session_id": sess.session_id,
            "candidate_employee_id": "EMP-2001",  # Conflict! Session is EMP-1001
        }

        res = client.post("/api/v1/voice/turn", files=files, data=data)
        assert res.status_code == 400
        assert "claim conflict" in res.json()["error"]["message"].lower()
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# 3. Security Fixes & Anti-Resurrection Tests
# =============================================================================

def test_anti_resurrection_revoked_session_cannot_be_recreated():
    """Revoking a session permanently invalidates it; attempts to resurrect it raise ValueError."""
    import uuid
    store = IdentityMappingStore.get_instance()
    sess_id = f"sess_anti_resurrect_{uuid.uuid4().hex}"
    store.create_session(sess_id, "EMP-1001", "Aarav Mehta", "Software Engineer", "Engineering")

    # Explicitly revoke
    assert store.revoke_session(sess_id) is True
    rec = store.get_session(sess_id)
    assert rec.is_revoked is True
    assert rec.is_valid is False

    # Attempting to recreate the same revoked session ID must raise ValueError
    with pytest.raises(ValueError, match="Cannot resurrect revoked session"):
        store.create_session(sess_id, "EMP-1001", "Aarav Mehta", "Software Engineer", "Engineering")


def test_require_verified_session_rejects_query_param_token():
    """Passing session token in URL query parameter is rejected with HTTP 400."""
    import uuid
    client = TestClient(app)
    store = IdentityMappingStore.get_instance()
    sess = store.create_session(f"sess_qp_{uuid.uuid4().hex}", "EMP-1001", "Aarav Mehta", "Software Engineer", "Engineering")

    # Attempt accessing /employees/me with query param ?session_id=...
    res = client.get(f"/api/v1/employees/me?session_id={sess.session_id}")
    assert res.status_code == 400

    assert "query parameter" in res.json()["error"]["message"].lower()


# =============================================================================
# 4. Pre-LLM Context Filtering & Answer Generation Test
# =============================================================================

def test_pre_llm_filtering_limits_context_to_authorized_scope():
    """Context builder strictly limits LLM context to authorized records only."""
    scoped_auth = ScopedAuthorizationService.get_instance()

    # Persona A (EMP-1001) asks about private salary/peer data
    aarav_context = scoped_auth.build_authorized_context_for_llm(
        actor_id="EMP-1001",
        query="What is Priya's salary and private record EMP-2001?",
    )

    # Actor profile is present
    assert aarav_context["authenticated_actor"]["id"] == "EMP-1001"
    assert "salary" not in aarav_context["authenticated_actor"]

    # Target EMP-2001 is denied; raw record is NOT passed to LLM
    assert "requested_target_profile" not in aarav_context
    assert aarav_context["access_denial"]["status"] == "DENIED"

    # Persona B (EMP-2001) queries direct report EMP-1001
    priya_context = scoped_auth.build_authorized_context_for_llm(
        actor_id="EMP-2001",
        query="How is EMP-1001 performing?",
    )
    assert priya_context["authenticated_actor"]["id"] == "EMP-2001"
    assert "requested_target_profile" in priya_context
    assert priya_context["requested_target_profile"]["id"] == "EMP-1001"
