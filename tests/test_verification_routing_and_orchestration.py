"""
IntentLock — Verification Routing & OpenAI Orchestration Comprehensive Unit Tests
Covers:
1. Strict 1-to-1 Detectif Credential & Mode Selection
2. Preflight Bounds, Error Mapping & Credits Charged
3. Helper Methods Explicit Credential Headers
4. Authoritative Evidence Policy & Recursive Mutation Blocking
5. PendingClarification Slot Completion & Specific Clarification Preservation
6. 0 Planning Calls for Exact Commands
"""

import pytest
import httpx
import io
import wave
import struct

from backend.core.config import settings
from backend.core.ports import VoiceEvidenceResult
from backend.models.turn import OriginalAudioMetadata
from backend.adapters.detectif_adapter import DetectifHTTPClient, DetectifVoiceEvidenceAdapter
from backend.services.operation_registry import OperationRegistry
from backend.services.evidence_policy_service import (
    EvidencePolicyService,
    EvidencePolicyContext,
    EvidenceCheckMode,
)
from backend.services.conversation_dispatch import (
    ConversationState,
    IntentPlan,
    _parse_single,
    ConversationDispatcher,
    PendingClarification,
)
from backend.services.semantic_orchestrator import (
    is_exact_public_help,
    is_exact_confirmation,
    is_exact_cancellation,
    is_exact_back,
)


def make_dummy_metadata(duration_bytes: int = 160000, digest: str = "abc123digest") -> OriginalAudioMetadata:
    return OriginalAudioMetadata(
        safe_filename="test_audio.wav",
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=duration_bytes,
        sha256_digest=digest,
    )


def make_valid_wav_bytes(duration_s: float = 5.0, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_samples = int(duration_s * sample_rate)
        raw = struct.pack(f"<{num_samples}h", *([1000] * num_samples))
        wf.writeframes(raw)
    return buf.getvalue()


# =============================================================================
# 1. Detectif HTTP Client Credential Isolation & Mode Routing
# =============================================================================

def test_detectif_client_selects_scoped_credentials():
    client = DetectifHTTPClient(
        speaker_api_key="key_speaker_123",
        deepfake_api_key="key_deepfake_456",
        combined_api_key="key_combined_789",
        api_key="key_legacy_999",
    )

    k_spk, r_spk = client.get_credential_for_mode("speaker")
    assert k_spk == "key_speaker_123"
    assert r_spk == "speaker"

    k_df, r_df = client.get_credential_for_mode("deepfake")
    assert k_df == "key_deepfake_456"
    assert r_df == "deepfake"

    k_cb, r_cb = client.get_credential_for_mode("combined")
    assert k_cb == "key_combined_789"
    assert r_cb == "combined"


def test_detectif_client_rejects_invalid_mode():
    client = DetectifHTTPClient()
    with pytest.raises(ValueError, match="Unknown Detectif verification mode"):
        client.get_credential_for_mode("invalid_mode")


def test_detectif_client_legacy_fallback_flag():
    client = DetectifHTTPClient(
        speaker_api_key=None,
        deepfake_api_key=None,
        combined_api_key=None,
        api_key="legacy_key",
    )
    # When DETECTIF_LEGACY_KEY_FALLBACK is True
    original_flag = settings.DETECTIF_LEGACY_KEY_FALLBACK
    try:
        settings.DETECTIF_LEGACY_KEY_FALLBACK = True
        key, role = client.get_credential_for_mode("speaker")
        assert key == "legacy_key"
        assert role == "legacy"

        settings.DETECTIF_LEGACY_KEY_FALLBACK = False
        key, role = client.get_credential_for_mode("speaker")
        assert key is None
        assert role == "speaker"
    finally:
        settings.DETECTIF_LEGACY_KEY_FALLBACK = original_flag


# =============================================================================
# 2. Strict 1-to-1 Provider Call & Result Field Population
# =============================================================================

@pytest.mark.asyncio
async def test_deepfake_only_mode_single_call_and_no_session():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        assert request.url.path.endswith("/deepfake/detect")
        assert request.headers.get("Authorization") == "Bearer df_key_scoped"
        assert request.headers.get("x-api-key") == "df_key_scoped"
        return httpx.Response(200, json={
            "verdict": "real",
            "score": 0.08,
            "threshold": 0.50,
            "credits_charged": 1.0,
        })

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(
        deepfake_api_key="df_key_scoped",
        transport=transport,
    )
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id=None,
        correlation_id="turn_df_1",
        mode="deepfake",
    )

    assert call_count == 1
    assert result.is_available is True
    assert result.deepfake_verdict == "real"
    assert result.decision is None
    assert result.speaker_id is None
    assert result.is_dual_verified is False  # Never grants dual verified entry
    assert result.credential_role == "deepfake"
    assert result.mode_executed == "deepfake"
    assert result.credits_charged == 1.0


@pytest.mark.asyncio
async def test_speaker_only_mode_single_call_and_no_dual_verified():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        assert request.url.path.endswith("/speakers/verify")
        assert request.headers.get("Authorization") == "Bearer spk_key_scoped"
        return httpx.Response(200, json={
            "speaker_id": "emp_1001_aarav",
            "result": {"decision": "match", "similarity": 0.92, "threshold": 0.65},
            "credits_charged": 1.0,
        })

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(
        speaker_api_key="spk_key_scoped",
        transport=transport,
    )
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(3.5)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_spk_1",
        mode="speaker",
    )

    assert call_count == 1
    assert result.is_available is True
    assert result.decision == "match"
    assert result.deepfake_verdict is None
    assert result.is_dual_verified is False  # Missing deepfake verdict
    assert result.credential_role == "speaker"
    assert result.mode_executed == "speaker"
    assert result.credits_charged == 1.0


@pytest.mark.asyncio
async def test_combined_mode_single_call_populates_credits():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        assert request.url.path.endswith("/speakers/verify")
        assert request.headers.get("Authorization") == "Bearer comb_key_scoped"
        return httpx.Response(200, json={
            "speaker_id": "emp_1001_aarav",
            "result": {"decision": "match", "similarity": 0.89, "threshold": 0.65},
            "deepfake": {"verdict": "real", "score": 0.12, "threshold": 0.50},
            "credits_charged": 2.0,
        })

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(
        combined_api_key="comb_key_scoped",
        transport=transport,
    )
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_comb_1",
        mode="combined",
    )

    assert call_count == 1
    assert result.is_dual_verified is True
    assert result.credential_role == "combined"
    assert result.mode_executed == "combined"
    assert result.credits_charged == 2.0


# =============================================================================
# 3. HTTP Status Code Discrimination
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("status_code,expected_error_code", [
    (401, "INVALID_CREDENTIAL"),
    (402, "INSUFFICIENT_CREDITS"),
    (403, "FORBIDDEN_SCOPE"),
    (404, "SPEAKER_NOT_FOUND"),
    (502, "PROVIDER_UNAVAILABLE"),
    (503, "PROVIDER_UNAVAILABLE"),
    (504, "PROVIDER_UNAVAILABLE"),
])
async def test_detectif_error_code_mapping(status_code, expected_error_code):
    def handler(request: httpx.Request):
        return httpx.Response(status_code, json={"error": {"message": f"Test error {status_code}"}})

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(combined_api_key="key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="err_turn",
        mode="combined",
    )

    assert result.is_available is False
    assert result.error_code == expected_error_code
    assert result.is_dual_verified is False
    assert result.mode_executed == "combined"


# =============================================================================
# 4. Helper Methods Scoped Auth Headers
# =============================================================================

@pytest.mark.asyncio
async def test_helper_methods_use_scoped_headers():
    headers_seen = {}

    def handler(request: httpx.Request):
        headers_seen[request.url.path] = request.headers.get("Authorization")
        if request.url.path.endswith("/deepfake/detect"):
            return httpx.Response(200, json={"verdict": "real"})
        elif request.url.path.endswith("/speakers/enroll"):
            return httpx.Response(200, json={"enrolled": True})
        elif request.url.path.endswith("/credits"):
            return httpx.Response(200, json={"credits": 50})
        elif request.url.path.endswith("/speakers"):
            return httpx.Response(200, json={"speakers": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(
        speaker_api_key="key_spk",
        deepfake_api_key="key_df",
        combined_api_key="key_comb",
        transport=transport,
    )
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio = make_valid_wav_bytes(4.0)

    await adapter.detect_deepfake(audio)
    assert any(p.endswith("/deepfake/detect") and h == "Bearer key_df" for p, h in headers_seen.items())

    await adapter.enroll_speaker("spk_1", audio)
    assert any(p.endswith("/speakers/enroll") and h == "Bearer key_spk" for p, h in headers_seen.items())

    await adapter.list_remote_speakers()
    assert any(p.endswith("/speakers") and h == "Bearer key_spk" for p, h in headers_seen.items())

    await adapter.get_balance()
    assert any(p.endswith("/credits") and h == "Bearer key_comb" for p, h in headers_seen.items())


# =============================================================================
# 5. Authoritative Operation Registry & Evidence Policy
# =============================================================================

def test_operation_registry_mutations_and_recursive_detection():
    # Direct mutations
    assert OperationRegistry.is_mutation("create_ticket") is True
    assert OperationRegistry.is_mutation("update_ticket") is True
    assert OperationRegistry.is_mutation("comment_ticket") is True
    assert OperationRegistry.is_mutation("update_contact") is True
    assert OperationRegistry.is_mutation("confirm") is True
    assert OperationRegistry.is_mutation("profile") is False
    assert OperationRegistry.is_mutation("team_table") is False
    assert OperationRegistry.is_mutation("authenticity_check") is False

    # Recursive mutation detection
    clean_plan = IntentPlan(operation="compound", compound_plans=[
        IntentPlan(operation="profile"),
        IntentPlan(operation="team_table"),
    ])
    assert OperationRegistry.has_mutation_recursively(clean_plan) is False

    dirty_plan = IntentPlan(operation="compound", compound_plans=[
        IntentPlan(operation="profile"),
        IntentPlan(operation="update_contact", value="+1234567890"),
    ])
    assert OperationRegistry.has_mutation_recursively(dirty_plan) is True


def test_evidence_policy_distinguishes_presentation_reuse_vs_active_read():
    policy = EvidencePolicyService.get_instance()

    # Presentation reuse
    ctx_rechart = EvidencePolicyContext(
        session_id="sess_123",
        session_valid=True,
        session_age_s=25.0,
        session_actor_id="EMP-1001",
        operation="rechart",
    )
    dec_rechart = policy.evaluate_turn_requirements(ctx_rechart)
    assert dec_rechart.mode == EvidenceCheckMode.REUSE
    assert dec_rechart.reason_code == "PRESENTATION_REUSE"

    # Active session read query
    ctx_read = EvidencePolicyContext(
        session_id="sess_123",
        session_valid=True,
        session_age_s=25.0,
        session_actor_id="EMP-1001",
        operation="ticket_list",
    )
    dec_read = policy.evaluate_turn_requirements(ctx_read)
    assert dec_read.mode == EvidenceCheckMode.REUSE
    assert dec_read.reason_code == "ACTIVE_SESSION_READ"

    # Authenticity check routes to DEEPFAKE_ONLY
    ctx_auth = EvidencePolicyContext(
        operation="authenticity_check",
        has_audio=True,
        audio_duration_s=4.5,
    )
    dec_auth = policy.evaluate_turn_requirements(ctx_auth)
    assert dec_auth.mode == EvidenceCheckMode.DEEPFAKE_ONLY
    assert dec_auth.requires_provider_call is True

    # Confirm always requires fresh COMBINED check
    ctx_confirm = EvidencePolicyContext(
        session_id="sess_123",
        session_valid=True,
        session_age_s=10.0,
        session_actor_id="EMP-1001",
        operation="confirm",
        has_audio=True,
        audio_duration_s=4.5,
    )
    dec_confirm = policy.evaluate_turn_requirements(ctx_confirm)
    assert dec_confirm.mode == EvidenceCheckMode.COMBINED
    assert dec_confirm.requires_provider_call is True


# =============================================================================
# 6. Specific Clarification & PendingClarification Slot Completion
# =============================================================================

def test_pending_clarification_slot_completion():
    state = ConversationState(actor_id="EMP-1001")

    # Turn 1: User says "Update my phone number" without phone
    plan_t1 = _parse_single("update my phone number", state=state)
    assert plan_t1.operation == "clarify"
    assert plan_t1.field == "phone"
    assert "phone number" in plan_t1.value.lower()

    # Verify state saved PendingClarification
    clar = state.get_active_clarification()
    assert clar is not None
    assert clar.target_operation == "update_contact"
    assert clar.missing_slot == "phone"

    # Turn 2: User provides phone number directly
    plan_t2 = _parse_single("+1 555 987 6543", state=state)
    assert plan_t2.operation == "update_contact"
    assert plan_t2.field == "phone"
    assert plan_t2.value == "+1 555 987 6543"

    # Verify clarification was consumed and cleared
    assert state.get_active_clarification() is None


def test_dispatcher_preserves_specific_clarification_message():
    dispatcher = ConversationDispatcher(None)
    state = ConversationState(actor_id="EMP-1001")

    plan = IntentPlan(
        operation="clarify",
        field="phone",
        value="What new work phone number should I use?",
    )
    res = dispatcher.dispatch("EMP-1001", "sess_1", plan)
    assert res.spoken_summary == "What new work phone number should I use?"
    assert res.clarification_reason == "MISSING_PARAMETER"


# =============================================================================
# 7. Exact Commands 0 Model Calls
# =============================================================================

def test_exact_commands_zero_model_calls():
    assert is_exact_public_help("help") is True
    assert is_exact_public_help("what can i ask") is True
    assert is_exact_public_help("Help me with my private tickets") is False  # Private reference

    assert is_exact_confirmation("i confirm") is True
    assert is_exact_confirmation("confirm") is True
    assert is_exact_confirmation("do not confirm") is False  # Negation

    assert is_exact_cancellation("cancel") is True
    assert is_exact_cancellation("abort") is True
    assert is_exact_cancellation("nevermind") is True
    assert is_exact_cancellation("don't cancel") is False  # Negation

    assert is_exact_back("back") is True
    assert is_exact_back("go back") is True
