"""Local preview is bounded and untrusted; it cannot authenticate or call paid models."""
from types import SimpleNamespace
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest
from backend.voice_preview import register_voice_preview


class LocalSTT:
    calls = 0

    def is_ready(self):
        return True

    async def transcribe(self, metadata, audio, turn_id):
        assert audio[:4] == b"RIFF"
        self.calls += 1
        return SimpleNamespace(transcript="This is an actual local adapter result")


class LocalVAD:
    def validate_speech(self, samples):
        return SimpleNamespace(has_speech=True, offset_s=len(samples) / 16000)


def make_app(stt=None, vad=None):
    app = FastAPI()
    config = SimpleNamespace(API_V1_PREFIX="/api/v1", FRONTEND_ORIGINS=["http://localhost:5173"])
    register_voice_preview(app, config, lambda: stt, lambda: vad)
    return app


def test_origin_is_required_and_cross_origin_is_rejected():
    with TestClient(make_app(LocalSTT(), LocalVAD())) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/voice/preview", headers={"origin": "https://untrusted.example"}):
                pass
        assert exc.value.code == 1008


def test_missing_models_reports_unavailable_without_authentication():
    with TestClient(make_app()) as client:
        with client.websocket_connect("/api/v1/voice/preview", headers={"origin": "http://localhost:5173"}) as ws:
            assert ws.receive_json()["type"] == "unavailable"


def test_partial_and_vad_events_are_local_only_and_bad_frames_close():
    stt = LocalSTT()
    with TestClient(make_app(stt, LocalVAD())) as client:
        with client.websocket_connect("/api/v1/voice/preview", headers={"origin": "http://localhost:5173"}) as ws:
            ready = ws.receive_json()
            assert ready["sample_rate"] == 16000
            assert "session" not in ready
            for _ in range(5):
                ws.send_bytes(b"\x01\x00" * 5120)
            events = [ws.receive_json() for _ in range(6)]
            assert any(event["type"] == "vad" and event["speech"] for event in events)
            assert any(event["type"] == "transcript.partial" for event in events)
            assert stt.calls == 1
            ws.send_bytes(b"odd")
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008


def test_preview_does_not_mount_test_or_knowledge_routes():
    with TestClient(make_app(LocalSTT(), LocalVAD())) as client:
        assert client.get("/api/test/fixtures").status_code == 404
        assert client.get("/api/v1/employees").status_code == 404
