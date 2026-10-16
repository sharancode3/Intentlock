"""
IntentLock — Detectif Adapter Contract & Resilience Tests
Exercises mock transport verification of the DetectifVoiceEvidenceAdapter
without making external network requests or consuming live API credits.
"""

import json
import pytest
import httpx
from backend.adapters.detectif_adapter import DetectifVoiceEvidenceAdapter, DetectifHTTPClient
from backend.models.turn import OriginalAudioMetadata
from backend.core.ports import VoiceEvidenceResult


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
    import wave
    import struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_samples = int(duration_s * sample_rate)
        raw = struct.pack(f"<{num_samples}h", *([1000] * num_samples))
        wf.writeframes(raw)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_verify_success_dual_check_match_and_real():
    """Valid match + real authenticity produces is_dual_verified == True."""
    def handler(request: httpx.Request):
        assert request.url.path == "/v1/speakers/verify"
        assert request.headers.get("Authorization") == "Bearer test_secret_key"
        assert "Idempotency-Key" in request.headers

        payload = {
            "speaker_id": "emp_1001_aarav",
            "request_id": "req_det_001",
            "result": {
                "decision": "match",
                "similarity": 0.88,
                "threshold": 0.65,
            },
            "deepfake": {
                "verdict": "real",
                "score": 0.12,
                "threshold": 0.50,
                "model": "v1_audio_authenticity",
            },
        }
        return httpx.Response(200, json=payload, headers={"x-request-id": "req_det_001"})

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(
        base_url="https://platform.detectif.ai/v1",
        api_key="test_secret_key",
        transport=transport,
    )
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert result.is_available is True
    assert result.decision == "match"
    assert result.similarity_score == 0.88
    assert result.deepfake_verdict == "real"
    assert result.deepfake_score == 0.12
    assert result.is_dual_verified is True
    assert result.speaker_id == "emp_1001_aarav"
    assert result.error_code is None


@pytest.mark.asyncio
async def test_verify_fails_on_speaker_no_match():
    """Speaker mismatch with genuine human speech fails dual verification."""
    def handler(request: httpx.Request):
        payload = {
            "speaker_id": "emp_1001_aarav",
            "result": {
                "decision": "no_match",
                "similarity": 0.22,
                "threshold": 0.65,
            },
            "deepfake": {
                "verdict": "real",
                "score": 0.05,
            },
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(api_key="test_key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert result.decision == "no_match"
    assert result.deepfake_verdict == "real"
    assert result.is_dual_verified is False


@pytest.mark.asyncio
async def test_verify_fails_on_deepfake_synthetic():
    """Speaker match with synthetic / deepfake audio fails dual verification."""
    def handler(request: httpx.Request):
        payload = {
            "speaker_id": "emp_1001_aarav",
            "result": {
                "decision": "match",
                "similarity": 0.91,
                "threshold": 0.65,
            },
            "deepfake": {
                "verdict": "fake",
                "score": 0.94,
            },
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(api_key="test_key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert result.decision == "match"
    assert result.deepfake_verdict == "fake"
    assert result.is_dual_verified is False


@pytest.mark.asyncio
async def test_verify_fails_on_identity_correspondence_mismatch():
    """When provider returns a speaker ID differing from candidate, verification fails."""
    def handler(request: httpx.Request):
        payload = {
            "speaker_id": "emp_9999_wrong",
            "result": {"decision": "match", "similarity": 0.9},
            "deepfake": {"verdict": "real"},
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(api_key="test_key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert result.error_code == "IDENTITY_CORRESPONDENCE_MISMATCH"
    assert result.is_dual_verified is False


@pytest.mark.asyncio
async def test_verify_rejects_audio_shorter_than_4s():
    """Audio shorter than 4.0s is rejected before provider call."""
    called = False
    def handler(request: httpx.Request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(api_key="test_key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(2.5)  # 2.5s < 4.0s
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert called is False
    assert result.error_code == "AUDIO_TOO_SHORT"
    assert result.is_dual_verified is False


@pytest.mark.asyncio
async def test_verify_retries_on_rate_limit_429():
    """Adapter retries on HTTP 429 honoring Retry-After."""
    attempts = 0
    def handler(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"retry-after": "0.01"})
        return httpx.Response(
            200,
            json={
                "speaker_id": "emp_1001_aarav",
                "result": {"decision": "match", "similarity": 0.8},
                "deepfake": {"verdict": "real", "score": 0.1},
            },
        )

    transport = httpx.MockTransport(handler)
    client_wrapper = DetectifHTTPClient(api_key="test_key", transport=transport)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert attempts == 2
    assert result.is_dual_verified is True


@pytest.mark.asyncio
async def test_verify_unconfigured_fails_closed():
    """Unconfigured adapter fails closed without network attempts."""
    client_wrapper = DetectifHTTPClient(api_key=None)
    adapter = DetectifVoiceEvidenceAdapter(http_client=client_wrapper)

    audio_bytes = make_valid_wav_bytes(5.0)
    meta = make_dummy_metadata(len(audio_bytes))

    result = await adapter.verify_evidence(
        audio_metadata=meta,
        audio_bytes=audio_bytes,
        candidate_speaker_id="emp_1001_aarav",
        correlation_id="turn_123",
    )

    assert result.is_available is False
    assert result.error_code == "DETECTIF_UNCONFIGURED"
    assert result.is_dual_verified is False
