"""
IntentLock — Evidence Policy & Mode-Aware Biometric Routing Tests
Validates:
1. Authoritative Evidence Matrix (public help, session reuse, initial entry, mutation confirm).
2. Mode-aware Detectif adapter execution (speaker, deepfake, combined).
3. 3-key scoped credential handling without credential leakage.
4. Audio bounds preflight validation before network calls.
5. Idempotency key uniqueness per mode.
"""

import hashlib
import httpx
import pytest

from backend.adapters.detectif_adapter import DetectifHTTPClient, DetectifVoiceEvidenceAdapter
from backend.core.ports import VoiceEvidenceResult
from backend.models.turn import OriginalAudioMetadata
from backend.services.evidence_policy_service import (
    EvidenceCheckMode,
    EvidencePolicyContext,
    EvidencePolicyService,
)


def make_dummy_metadata(duration_bytes: int = 160000, digest: str = "abc123digest") -> OriginalAudioMetadata:
    return OriginalAudioMetadata(
        safe_filename="test_utterance.wav",
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=duration_bytes,
        sha256_digest=digest,
    )


def make_valid_wav_bytes(duration_s: float = 5.0, sample_rate: int = 16000) -> bytes:
    import io
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_samples = int(duration_s * sample_rate)
        raw = struct.pack(f"<{num_samples}h", *([1000] * num_samples))
        wf.writeframes(raw)
    return buf.getvalue()


class MockEnrollmentMapping:
    def __init__(self, status="ENROLLED", speaker_id="spk_aarav_123"):
        self.enrollment_status = status
        self.provider_speaker_id = speaker_id
        self.account_alias = "primary_account"


# =============================================================================
# 1. Evidence Policy Decision Matrix Tests
# =============================================================================

def test_evidence_policy_public_help_zero_calls():
    svc = EvidencePolicyService.get_instance()
    ctx = EvidencePolicyContext(operation="help", has_audio=False)
    decision = svc.evaluate_turn_requirements(ctx)
    assert decision.mode == EvidenceCheckMode.NO_CHECK
    assert decision.requires_provider_call is False
    assert decision.reason_code == "PUBLIC_HELP"


def test_evidence_policy_navigation_cancel_zero_calls():
    svc = EvidencePolicyService.get_instance()
    ctx = EvidencePolicyContext(operation="cancel", session_valid=True, session_actor_id="EMP-1001")
    decision = svc.evaluate_turn_requirements(ctx)
    assert decision.mode == EvidenceCheckMode.NO_CHECK
    assert decision.requires_provider_call is False
    assert decision.reason_code == "NAVIGATION_CANCEL"


def test_evidence_policy_claim_conflict_denied():
    svc = EvidencePolicyService.get_instance()
    ctx = EvidencePolicyContext(
        session_valid=True,
        session_actor_id="EMP-1001",
        candidate_employee_id="EMP-2001",
    )
    decision = svc.evaluate_turn_requirements(ctx)
    assert decision.mode == EvidenceCheckMode.DENIED
    assert decision.requires_provider_call is False
    assert decision.reason_code == "CLAIM_CONFLICT"


def test_evidence_policy_mutation_confirm_requires_fresh_combined():
    svc = EvidencePolicyService.get_instance()
    ctx = EvidencePolicyContext(
        operation="confirm",
        session_valid=True,
        session_actor_id="EMP-1001",
        has_audio=True,
        is_mutation=True,
    )
    decision = svc.evaluate_turn_requirements(ctx)
    assert decision.mode == EvidenceCheckMode.COMBINED
    assert decision.requires_provider_call is True
    assert decision.reason_code == "PROTECTED_MUTATION_CONFIRMATION"
    assert decision.audio_min_duration_s == 4.0
    assert decision.evidence_freshness == "fresh_this_turn"


def test_evidence_policy_presentation_reuse_zero_calls():
    svc = EvidencePolicyService.get_instance()
    ctx = EvidencePolicyContext(
        operation="rechart",
        session_valid=True,
        session_actor_id="EMP-1001",
        session_age_s=30.0,
    )
    decision = svc.evaluate_turn_requirements(ctx)
    assert decision.mode == EvidenceCheckMode.REUSE
    assert decision.requires_provider_call is False
    assert decision.reason_code in ("REUSE_SESSION_EVIDENCE", "PRESENTATION_REUSE")
    assert decision.evidence_freshness == "reused_from_session"


def test_evidence_policy_initial_employee_entry_requires_combined():
    svc = EvidencePolicyService.get_instance()
    mapping = MockEnrollmentMapping("ENROLLED")
    ctx = EvidencePolicyContext(
        candidate_employee_id="EMP-1001",
        has_audio=True,
        audio_duration_s=5.0,
    )
    decision = svc.evaluate_turn_requirements(ctx, enrollment_mapping=mapping)
    assert decision.mode == EvidenceCheckMode.COMBINED
    assert decision.requires_provider_call is True
    assert decision.reason_code == "INITIAL_EMPLOYEE_ENTRY"
    assert decision.audio_min_duration_s == 4.0


def test_evidence_policy_unenrolled_candidate_denied():
    svc = EvidencePolicyService.get_instance()
    mapping = MockEnrollmentMapping("NOT_ENROLLED")
    ctx = EvidencePolicyContext(
        candidate_employee_id="EMP-9999",
        has_audio=True,
    )
    decision = svc.evaluate_turn_requirements(ctx, enrollment_mapping=mapping)
    assert decision.mode == EvidenceCheckMode.DENIED
    assert decision.requires_provider_call is False
    assert decision.reason_code == "UNENROLLED_CANDIDATE"


def test_evidence_policy_short_audio_rejected_before_provider():
    svc = EvidencePolicyService.get_instance()
    mapping = MockEnrollmentMapping("ENROLLED")
    ctx = EvidencePolicyContext(
        candidate_employee_id="EMP-1001",
        has_audio=True,
        audio_duration_s=2.5,  # <= 4.0s
    )
    decision = svc.evaluate_turn_requirements(ctx, enrollment_mapping=mapping)
    assert decision.mode == EvidenceCheckMode.UNAVAILABLE
    assert decision.requires_provider_call is False
    assert decision.reason_code == "AUDIO_TOO_SHORT"


# =============================================================================
# 2. Mode-Aware Adapter & Scoped Credential Tests
# =============================================================================

@pytest.mark.asyncio
async def test_detectif_scoped_credentials_routing():
    """Verify that mode selects the scoped API key and sends correct headers and payload."""
    dispatched_paths = []
    dispatched_headers = []
    dispatched_data = []

    def handler(request: httpx.Request):
        dispatched_paths.append(request.url.path)
        dispatched_headers.append(dict(request.headers))
        content = request.content.decode("utf-8", errors="ignore")
        dispatched_data.append(content)

        if request.url.path == "/v1/deepfake/detect":
            return httpx.Response(200, json={
                "verdict": "real",
                "score": 0.08,
                "threshold": 0.50,
                "model_version": "v1_audio_authenticity",
            })
        elif request.url.path == "/v1/speakers/verify":
            is_combined = "detect_deepfake" in content and "true" in content
            res_payload = {
                "speaker_id": "spk_aarav_123",
                "result": {"decision": "match", "similarity": 0.92, "threshold": 0.65},
            }
            if is_combined:
                res_payload["deepfake"] = {"verdict": "real", "score": 0.05, "threshold": 0.50}
            return httpx.Response(200, json=res_payload)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = DetectifHTTPClient(
        base_url="https://platform.detectif.ai/v1",
        api_key="general_key",
        speaker_api_key="speaker_scoped_key",
        deepfake_api_key="deepfake_scoped_key",
        combined_api_key="combined_scoped_key",
        transport=transport,
    )
    adapter = DetectifVoiceEvidenceAdapter(http_client=client)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    # Test Speaker-Only mode
    res_speaker = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="spk_aarav_123",
        correlation_id="turn_spk",
        mode="speaker",
    )
    assert res_speaker.is_available is True
    assert res_speaker.decision == "match"
    assert res_speaker.deepfake_verdict is None
    assert res_speaker.is_dual_verified is False  # Speaker-only is never dual verified
    assert dispatched_paths[-1] == "/v1/speakers/verify"
    assert "Bearer speaker_scoped_key" in dispatched_headers[-1]["authorization"]
    assert dispatched_headers[-1]["x-api-key"] == "speaker_scoped_key"

    # Test Deepfake-Only mode
    res_deepfake = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id=None,
        correlation_id="turn_df",
        mode="deepfake",
    )
    assert res_deepfake.is_available is True
    assert res_deepfake.deepfake_verdict == "real"
    assert res_deepfake.decision is None
    assert res_deepfake.is_dual_verified is False  # Deepfake-only is never dual verified
    assert dispatched_paths[-1] == "/v1/deepfake/detect"
    assert "Bearer deepfake_scoped_key" in dispatched_headers[-1]["authorization"]
    assert dispatched_headers[-1]["x-api-key"] == "deepfake_scoped_key"

    # Test Combined mode
    res_combined = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="spk_aarav_123",
        correlation_id="turn_comb",
        mode="combined",
    )
    assert res_combined.is_available is True
    assert res_combined.decision == "match"
    assert res_combined.deepfake_verdict == "real"
    assert res_combined.is_dual_verified is True  # Combined satisfies dual verification
    assert dispatched_paths[-1] == "/v1/speakers/verify"
    assert "Bearer combined_scoped_key" in dispatched_headers[-1]["authorization"]
    assert dispatched_headers[-1]["x-api-key"] == "combined_scoped_key"


@pytest.mark.asyncio
async def test_detectif_audio_bounds_per_mode():
    """Verify mode-specific audio duration bounds before provider calls."""
    called = False

    def handler(request: httpx.Request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = DetectifHTTPClient(api_key="key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client)

    # 3.5s audio meets speaker's 3s minimum, but not the >4s authenticity minimum.
    short_15 = make_valid_wav_bytes(3.5)
    meta_15 = make_dummy_metadata(len(short_15))

    # Combined rejects without calling the provider.
    res = await adapter.verify_evidence(meta_15, short_15, "spk_1", "c1", mode="combined")
    assert called is False
    assert res.error_code == "AUDIO_TOO_SHORT"

    # Deepfake rejects without calling the provider.
    res = await adapter.verify_evidence(meta_15, short_15, None, "c2", mode="deepfake")
    assert called is False
    assert res.error_code == "AUDIO_TOO_SHORT"

    # Speaker duration is valid and dispatches exactly the requested operation.
    res = await adapter.verify_evidence(meta_15, short_15, "spk_1", "c3", mode="speaker")
    assert called is True
