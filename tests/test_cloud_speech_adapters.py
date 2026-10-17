"""
IntentLock — Cloud Speech Adapters Offline Test Suite
Verifies OpenAISpeechInputAdapter and OpenAISpeechOutputAdapter contracts,
error handling, and zero-RAM cloud speech operation without live API calls.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.adapters.speech_stt import OpenAISpeechInputAdapter
from backend.adapters.speech_tts import OpenAISpeechOutputAdapter
from backend.core.ports import (
    UnavailableSpeechInputAdapter,
    UnavailableSpeechOutputAdapter,
)
from backend.core.config import Settings
from backend.models.turn import OriginalAudioMetadata


@pytest.fixture
def sample_audio_metadata():
    return OriginalAudioMetadata(
        safe_filename="sample.wav",
        declared_content_type="audio/wav",
        normalized_mime_type="audio/wav",
        byte_count=1024,
        sha256_digest="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )


@pytest.mark.asyncio
async def test_openai_speech_input_unconfigured(sample_audio_metadata):
    adapter = OpenAISpeechInputAdapter(api_key="")
    assert not adapter.is_available
    res = await adapter.transcribe(sample_audio_metadata, b"fake_audio", "turn-1")
    assert not res.is_available
    assert "not configured" in res.error_message


@pytest.mark.asyncio
async def test_openai_speech_input_transcribe_success(sample_audio_metadata):
    adapter = OpenAISpeechInputAdapter(api_key="sk-test-key")
    assert adapter.is_available

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Show my open tickets"
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_resp)
    adapter._client = mock_client

    res = await adapter.transcribe(sample_audio_metadata, b"fake_wav", "turn-2")
    assert res.is_available
    assert res.transcript == "Show my open tickets"
    assert res.confidence == 0.98
    adapter.cleanup()
    assert adapter._client is None


@pytest.mark.asyncio
async def test_openai_speech_input_transcribe_error_handled(sample_audio_metadata):
    adapter = OpenAISpeechInputAdapter(api_key="sk-test-key")
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(side_effect=RuntimeError("API quota exceeded"))
    adapter._client = mock_client

    res = await adapter.transcribe(sample_audio_metadata, b"bytes", "turn-3")
    assert not res.is_available
    assert "API quota exceeded" in res.error_message


@pytest.mark.asyncio
async def test_openai_speech_output_unconfigured():
    adapter = OpenAISpeechOutputAdapter(api_key="")
    assert not adapter.is_available
    res = await adapter.synthesize("Hello", "turn-1")
    assert not res.is_available
    assert "not configured" in res.error_message


@pytest.mark.asyncio
async def test_openai_speech_output_empty_text():
    adapter = OpenAISpeechOutputAdapter(api_key="sk-test-key")
    res = await adapter.synthesize("   ", "turn-empty")
    assert res.is_available
    assert res.audio_bytes is None
    assert res.error_message == "EMPTY_TEXT"


@pytest.mark.asyncio
async def test_openai_speech_output_synthesize_success():
    adapter = OpenAISpeechOutputAdapter(api_key="sk-test-key", voice="alloy")
    assert adapter.is_available

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = b"RIFFmockwavcontent"
    mock_client.audio.speech.create = AsyncMock(return_value=mock_resp)
    adapter._client = mock_client

    res = await adapter.synthesize("Welcome Aarav, you have 2 open tickets.", "turn-4")
    assert res.is_available
    assert res.audio_bytes == b"RIFFmockwavcontent"
    assert res.audio_format == "audio/wav"
    assert res.error_message is None
    adapter.cleanup()
    assert adapter._client is None


@pytest.mark.asyncio
async def test_openai_speech_output_synthesize_error_handled():
    adapter = OpenAISpeechOutputAdapter(api_key="sk-test-key")
    mock_client = MagicMock()
    mock_client.audio.speech.create = AsyncMock(side_effect=RuntimeError("Rate limit reached"))
    adapter._client = mock_client

    res = await adapter.synthesize("Test error", "turn-5")
    assert not res.is_available
    assert "Rate limit reached" in res.error_message


@pytest.mark.asyncio
async def test_unavailable_speech_adapters(sample_audio_metadata):
    input_adapter = UnavailableSpeechInputAdapter()
    in_res = await input_adapter.transcribe(sample_audio_metadata, b"test", "turn-fail")
    assert not in_res.is_available

    output_adapter = UnavailableSpeechOutputAdapter()
    out_res = await output_adapter.synthesize("test", "turn-fail")
    assert not out_res.is_available


def test_safe_diagnostics_no_secret_leak():
    s = Settings(
        OPENAI_API_KEY="sk-super-secret-123456",
        DETECTIF_API_KEY="det-secret-7890",
        OPERATOR_SECRET_KEY="op-secret-abc",
        SUPABASE_SERVICE_ROLE_KEY="sb-secret-xyz",
    )
    diag = s.get_safe_diagnostics()
    # Confirm no raw keys are in the diagnostics dict
    diag_str = str(diag)
    assert "sk-super-secret-123456" not in diag_str
    assert "det-secret-7890" not in diag_str
    assert "op-secret-abc" not in diag_str
    assert "sb-secret-xyz" not in diag_str
    assert diag["openai_configured"] is True
    assert diag["detectif_configured"] is True
    assert diag["operator_key_configured"] is True
