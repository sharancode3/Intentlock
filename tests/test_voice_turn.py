"""
IntentLock — Voice Turn Ingress Test Suite
Validates transport bounds, MIME type normalization, empty/oversized audio handling,
request correlation, and the canonical Stage 1 unavailable response envelope.
"""

import io
import pytest
from starlette.testclient import TestClient
from backend.main import app
from backend.core.config import settings


@pytest.fixture(scope="module")
def client():
    """Inject unavailable adapters for offline Stage 1 foundation tests."""
    from backend.core.ports import UnavailableSpeechInputAdapter, UnavailableSpeechOutputAdapter
    from backend.main import get_speech_input_port, get_speech_output_port

    app.dependency_overrides[get_speech_input_port] = lambda: UnavailableSpeechInputAdapter()
    app.dependency_overrides[get_speech_output_port] = lambda: UnavailableSpeechOutputAdapter()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_valid_voice_turn_returns_canonical_unavailable_envelope(client):
    """A valid audio upload receives the documented Stage 1 unavailable response (HTTP 503)."""
    fake_audio = b"\x1a\x45\xdf\xa3" + b"\x00" * 1024  # Small WebM header mock
    files = {
        "audio_file": ("utterance.webm", io.BytesIO(fake_audio), "audio/webm"),
    }
    data = {
        "client_turn_id": "turn-uuid-1234-abcd",
        "client_timestamp": "2026-10-16T12:00:00Z",
    }

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 503

    body = res.json()
    assert body["api_version"] == "1"
    assert body["client_turn_id"] == "turn-uuid-1234-abcd"
    assert body["status"] == "unavailable"
    assert body["session"]["state"] == "ANONYMOUS"
    assert body["session"]["sessionId"] is None
    assert body["transcript"] is None
    assert body["assistant_message"] is None
    assert body["result_block"] is None
    assert body["trust_evidence"] is None
    assert body["error"]["code"] == "VOICE_PIPELINE_NOT_READY"
    assert body["error"]["retryable"] is False

    # Verify response headers
    assert "X-Request-Id" in res.headers
    assert res.headers["X-Request-Id"] == body["request_id"]
    assert "no-store" in res.headers.get("Cache-Control", "")


def test_voice_turn_browser_codec_parameters_accepted(client):
    """Browser MIME types with parameters (audio/webm;codecs=opus) must be normalized safely."""
    fake_audio = b"RIFF" + b"\x00" * 512
    files = {
        "audio_file": ("recording.webm", io.BytesIO(fake_audio), "audio/webm;codecs=opus"),
    }
    data = {"client_turn_id": "turn-browser-codec-test"}

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 503
    assert res.json()["status"] == "unavailable"


def test_voice_turn_unsupported_mime_type_rejected(client):
    """Non-audio MIME types must be rejected with HTTP 415."""
    fake_file = b"NOT_AUDIO_DATA"
    files = {
        "audio_file": ("test.txt", io.BytesIO(fake_file), "text/plain"),
    }
    data = {"client_turn_id": "turn-invalid-mime"}

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 415
    assert "Unsupported audio media type" in res.json()["error"]["message"]


def test_voice_turn_empty_audio_rejected(client):
    """Empty audio files (0 bytes) must be rejected with HTTP 400."""
    files = {
        "audio_file": ("empty.wav", io.BytesIO(b""), "audio/wav"),
    }
    data = {"client_turn_id": "turn-empty-audio"}

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 400
    assert "empty" in res.json()["error"]["message"].lower()


def test_voice_turn_missing_client_turn_id_rejected(client):
    """Blank or whitespace-only client_turn_id must be rejected with HTTP 400."""
    files = {
        "audio_file": ("test.wav", io.BytesIO(b"some-audio-content"), "audio/wav"),
    }
    data = {"client_turn_id": "   "}

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 400


def test_voice_turn_oversized_audio_rejected(monkeypatch, client):
    """Uploads exceeding MAX_AUDIO_BYTES must abort and return HTTP 413."""
    monkeypatch.setattr(settings, "MAX_AUDIO_BYTES", 1024)

    oversized_data = b"0" * 2048
    files = {
        "audio_file": ("too_large.wav", io.BytesIO(oversized_data), "audio/wav"),
    }
    data = {"client_turn_id": "turn-oversized"}

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 413
    assert "exceeds" in res.json()["error"]["message"].lower()


def test_streaming_request_bound_without_content_length_rejected(monkeypatch, client):
    """
    Ingress streaming bound must abort with 413 when total request payload exceeds
    MAX_REQUEST_BYTES even when Content-Length header is absent or streaming chunked.
    """
    monkeypatch.setattr(settings, "MAX_REQUEST_BYTES", 1024)

    boundary = "----TestBoundary12345"
    part_data = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="client_turn_id"\r\n\r\n'
        f"turn-test\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="audio_file"; filename="test.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8") + (b"A" * 2000) + f"\r\n--{boundary}--\r\n".encode("utf-8")

    def multipart_stream():
        chunk_size = 512
        for i in range(0, len(part_data), chunk_size):
            yield part_data[i : i + chunk_size]

    res = client.post(
        "/api/v1/voice/turn",
        content=multipart_stream(),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Request-Id": "test-chunked-multipart",
        },
    )
    assert res.status_code == 413
    assert "exceeds maximum limit" in res.json()["error"]["message"]



def test_voice_turn_client_session_id_does_not_grant_verified_state(client):
    """A client supplying session_id must not trick the server into a VERIFIED state."""
    fake_audio = b"AUDIO_BYTES_TEST"
    files = {
        "audio_file": ("turn.wav", io.BytesIO(fake_audio), "audio/wav"),
    }
    data = {
        "client_turn_id": "turn-session-test",
        "session_id": "forged_session_12345",
    }

    res = client.post("/api/v1/voice/turn", files=files, data=data)
    assert res.status_code == 503
    body = res.json()
    assert body["session"]["state"] == "ANONYMOUS"
    assert body["session"]["sessionId"] is None

