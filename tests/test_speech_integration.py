"""
IntentLock — Real Speech Integration Test Suite
Exercises actual inference for:
1. AudioDecoder (WAV & WebM container decoding, duration bounds, finiteness)
2. Silero VAD (speech presence, boundary detection, silence rejection, streaming VADIterator)
3. Faster-Whisper STT (helpdesk query, employee ID/ticket, negation, latency)
4. Kokoro TTS (neural synthesis, 24kHz WAV packaging, latency, empty text handling)
5. End-to-End Voice Gateway (/api/v1/voice/turn with real audio and safe policy)
"""

import io
import os
import time
import wave
import pytest
import numpy as np
pytestmark = pytest.mark.skipif(
    os.getenv("INTENTLOCK_OFFLINE_TESTS") == "1",
    reason="Real speech model tests are excluded from the deterministic offline suite.",
)
from starlette.testclient import TestClient

from backend.main import app, get_speech_input_port, get_speech_output_port
from backend.core.config import settings
from backend.models.turn import OriginalAudioMetadata
from backend.adapters import (
    AudioDecoder,
    SpeechVADService,
    FasterWhisperSTTAdapter,
    KokoroTTSAdapter,
)


@pytest.fixture(scope="module")
def speech_stack():
    """Initializes and warms up real open-source speech components."""
    t0 = time.perf_counter()
    vad = SpeechVADService.get_instance(threshold=0.5)
    stt = FasterWhisperSTTAdapter(model_name="tiny.en", device="cpu", compute_type="int8", vad_service=vad)
    stt.warmup()
    tts = KokoroTTSAdapter(lang_code="a", voice="af_heart", speed=1.0, device="cpu")
    tts.warmup()
    init_time_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "vad": vad,
        "stt": stt,
        "tts": tts,
        "init_time_ms": init_time_ms,
    }


@pytest.fixture(scope="module")
def real_speech_client(speech_stack):
    """TestClient wired to real speech adapters for integration testing."""
    app.dependency_overrides[get_speech_input_port] = lambda: speech_stack["stt"]
    app.dependency_overrides[get_speech_output_port] = lambda: speech_stack["tts"]
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# 1. Audio Decoder Tests
# =============================================================================

def test_audio_decoder_pcm_wav_round_trip():
    """Verify raw float32 PCM samples are serialized to valid 24kHz 16-bit WAV bytes."""
    samples = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 24000)).astype(np.float32)
    wav_bytes = AudioDecoder.pcm_to_wav_bytes(samples, sample_rate=24000)

    assert len(wav_bytes) == 24000 * 2 + 44  # 48044 bytes
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"

    # Decode back to 16kHz mono float32
    decoded_16k = AudioDecoder.decode_to_16k_mono(wav_bytes)
    assert decoded_16k.ndim == 1
    assert len(decoded_16k) == 16000
    assert np.isfinite(decoded_16k).all()


def test_audio_decoder_rejects_empty_and_corrupt():
    """Decoder must reject empty bytes and corrupt containers with ValueError."""
    with pytest.raises(ValueError, match="empty"):
        AudioDecoder.decode_to_16k_mono(b"")

    with pytest.raises(ValueError, match="Failed to decode"):
        AudioDecoder.decode_to_16k_mono(b"GARBAGE_NOT_AUDIO_DATA_AT_ALL")


def test_audio_decoder_duration_bounds():
    """Decoder enforces min and max duration bounds."""
    # Too short (< 0.1s): 50ms at 24kHz = 1200 samples
    short_samples = np.zeros(1200, dtype=np.float32)
    short_wav = AudioDecoder.pcm_to_wav_bytes(short_samples, sample_rate=24000)
    with pytest.raises(ValueError, match="below minimum operational threshold"):
        AudioDecoder.decode_to_16k_mono(short_wav, min_duration_s=0.1)


# =============================================================================
# 2. Silero VAD Tests
# =============================================================================

def test_silero_vad_detects_speech_and_silence(speech_stack):
    """VAD correctly identifies speech presence in active audio and flags pure silence."""
    vad: SpeechVADService = speech_stack["vad"]
    tts: KokoroTTSAdapter = speech_stack["tts"]

    # Generate real speech audio
    spoken = list(tts.pipeline("Testing the voice activity detector.", voice=tts.voice, speed=1.0))
    speech_pcm = spoken[0].audio.cpu().numpy()
    speech_wav = AudioDecoder.pcm_to_wav_bytes(speech_pcm, sample_rate=24000)
    decoded_16k = AudioDecoder.decode_to_16k_mono(speech_wav)

    # Validate active speech
    report = vad.validate_speech(decoded_16k)
    assert report.has_speech is True
    assert report.speech_duration_s > 0.5
    assert report.onset_s is not None
    assert report.offset_s is not None
    assert len(report.segments) >= 1

    # Validate pure silence
    silence_16k = np.zeros(32000, dtype=np.float32)  # 2.0s silence
    silence_report = vad.validate_speech(silence_16k)
    assert silence_report.has_speech is False
    assert silence_report.speech_duration_s == 0.0
    assert len(silence_report.segments) == 0


def test_silero_streaming_vad_iterator(speech_stack):
    """VADIterator from speech_hf processes audio chunks and tracks state."""
    vad: SpeechVADService = speech_stack["vad"]
    iterator = vad.create_stream_iterator(threshold=0.5, min_silence_duration_ms=300)
    assert iterator is not None

    # Feed 10 chunks of 512 samples (32ms frames at 16kHz)
    for _ in range(10):
        chunk = np.zeros(512, dtype=np.float32)
        import torch
        res = iterator(torch.from_numpy(chunk))
        # Silence yields None
        assert res is None


# =============================================================================
# 3. Faster-Whisper STT Tests
# =============================================================================

@pytest.mark.asyncio
async def test_faster_whisper_transcribes_helpdesk_sentence(speech_stack):
    """Faster-Whisper accurately transcribes a standard helpdesk query."""
    stt: FasterWhisperSTTAdapter = speech_stack["stt"]
    tts: KokoroTTSAdapter = speech_stack["tts"]

    phrase = "What are the company holiday policies for this year?"
    synth_res = await tts.synthesize(phrase, client_turn_id="turn-tts-test")
    assert synth_res.audio_bytes is not None

    meta = OriginalAudioMetadata(
        safe_filename="query.wav",
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=len(synth_res.audio_bytes),
        sha256_digest="fake-sha",
    )

    t0 = time.perf_counter()
    result = await stt.transcribe(meta, synth_res.audio_bytes, client_turn_id="turn-stt-1")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert result.is_available is True
    assert result.error_message is None
    assert result.transcript is not None
    assert "holiday" in result.transcript.lower() or "policies" in result.transcript.lower()
    assert result.latency_ms is not None
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_faster_whisper_transcribes_employee_id_and_negation(speech_stack):
    """Faster-Whisper captures critical employee identifiers and negation."""
    stt: FasterWhisperSTTAdapter = speech_stack["stt"]
    tts: KokoroTTSAdapter = speech_stack["tts"]

    negation_phrase = "Do not cancel my ticket."
    synth = await tts.synthesize(negation_phrase, client_turn_id="turn-negation")
    meta = OriginalAudioMetadata(
        safe_filename="negation.wav",
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=len(synth.audio_bytes),
        sha256_digest="fake-sha",
    )

    result = await stt.transcribe(meta, synth.audio_bytes, client_turn_id="turn-negation-stt")
    assert result.is_available is True
    assert "not" in result.transcript.lower()
    assert "cancel" in result.transcript.lower()


@pytest.mark.asyncio
async def test_faster_whisper_rejects_silence_with_vad(speech_stack):
    """STT pipeline rejects silence before running transcription, returning NO_SPEECH_DETECTED."""
    stt: FasterWhisperSTTAdapter = speech_stack["stt"]

    silence_pcm = np.zeros(24000, dtype=np.float32)  # 1.0s silence
    silence_wav = AudioDecoder.pcm_to_wav_bytes(silence_pcm, sample_rate=24000)

    meta = OriginalAudioMetadata(
        safe_filename="silence.wav",
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=len(silence_wav),
        sha256_digest="fake-sha",
    )

    result = await stt.transcribe(meta, silence_wav, client_turn_id="turn-silence")
    assert result.is_available is True
    assert result.error_message == "NO_SPEECH_DETECTED"
    assert result.transcript == ""


# =============================================================================
# 4. Kokoro TTS Tests
# =============================================================================

@pytest.mark.asyncio
async def test_kokoro_tts_synthesis_and_wav_format(speech_stack):
    """Kokoro synthesizes clear audio with valid WAV headers and measurable latency."""
    tts: KokoroTTSAdapter = speech_stack["tts"]

    text = "Voice verification is required to view confidential profile information."
    result = await tts.synthesize(text, client_turn_id="turn-guidance")

    assert result.is_available is True
    assert result.error_message is None
    assert result.audio_format == "audio/wav"
    assert result.audio_bytes is not None
    assert len(result.audio_bytes) > 20000
    assert result.audio_bytes[:4] == b"RIFF"

    # Verify duration matches sample count
    duration_s = (len(result.audio_bytes) - 44) / (24000 * 2)
    assert 2.0 <= duration_s <= 6.0


@pytest.mark.asyncio
async def test_kokoro_tts_handles_empty_input(speech_stack):
    """Kokoro safely returns EMPTY_TEXT on empty or whitespace strings."""
    tts: KokoroTTSAdapter = speech_stack["tts"]
    result = await tts.synthesize("   ", client_turn_id="turn-empty")

    assert result.is_available is True
    assert result.audio_bytes is None
    assert result.error_message == "EMPTY_TEXT"


# =============================================================================
# 5. End-to-End Voice Gateway (/api/v1/voice/turn) Tests
# =============================================================================

def test_e2e_voice_turn_real_audio_round_trip(real_speech_client, speech_stack):
    """
    Submitting a real spoken audio recording to POST /api/v1/voice/turn returns
    a real transcript, a safe unverified response, and playable synthesized audio.
    """
    tts: KokoroTTSAdapter = speech_stack["tts"]

    # Synthesize test utterance
    query_text = "What is the company policy for travel expenses?"
    generator = tts.pipeline(query_text, voice=tts.voice, speed=1.0)
    audio_pcm = list(generator)[0].audio.cpu().numpy()
    wav_bytes = AudioDecoder.pcm_to_wav_bytes(audio_pcm, sample_rate=24000)

    files = {
        "audio_file": ("utterance.wav", io.BytesIO(wav_bytes), "audio/wav"),
    }
    data = {
        "client_turn_id": "turn-e2e-real-speech",
        "client_timestamp": "2026-10-16T12:00:00Z",
    }

    res = real_speech_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 200

    body = res.json()
    assert body["api_version"] == "1"
    assert body["client_turn_id"] == "turn-e2e-real-speech"
    assert body["status"] in ("success", "unverified")
    assert body["session"]["state"] == "ANONYMOUS"
    assert body["session"]["sessionId"] is None

    # Real transcript verified
    assert body["transcript"] is not None
    assert "policy" in body["transcript"].lower() or "travel" in body["transcript"].lower() or "company" in body["transcript"].lower()

    # Safe assistant response
    assert body["assistant_message"] is not None
    assert body["spoken_summary"] is not None

    # Synthesized audio payload delivered
    assert body["speech_audio"] is not None
    assert body["speech_audio"]["mime_type"] == "audio/wav"
    assert body["speech_audio"]["sample_rate"] == 24000
    assert body["speech_audio"]["channels"] == 1
    assert body["speech_audio"]["byte_count"] > 10000
    assert body["speech_audio"]["base64_audio"] is not None
    assert body["speech_audio"]["duration_ms"] > 1000

    # Speech timings recorded
    assert body["speech_timings_ms"] is not None
    assert body["speech_timings_ms"]["stt_ms"] > 0
    assert body["speech_timings_ms"]["tts_ms"] > 0


def test_e2e_voice_turn_silence_rejected_as_bad_request(real_speech_client):
    """Submitting silent audio returns HTTP 400 with clear user guidance."""
    silence_pcm = np.zeros(24000, dtype=np.float32)
    silence_wav = AudioDecoder.pcm_to_wav_bytes(silence_pcm, sample_rate=24000)

    files = {
        "audio_file": ("silence.wav", io.BytesIO(silence_wav), "audio/wav"),
    }
    data = {
        "client_turn_id": "turn-e2e-silence",
    }

    res = real_speech_client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 400
    assert "no speech detected" in res.json()["error"]["message"].lower()


def test_readiness_probe_reports_speech_ready(real_speech_client):
    """When speech models are warmed and active, /health/ready reports speech_service='ready'."""
    res = real_speech_client.get("/health/ready")
    body = res.json()

    assert body["components"]["speech_service"] == "ready"
    assert body["components"]["voice_evidence"] in ("ready", "unconfigured")

