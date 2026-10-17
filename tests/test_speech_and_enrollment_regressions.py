"""Isolated regressions: no live credentials, database writes or paid API calls."""
import asyncio
import json
import io
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from backend.adapters.cloud_speech_preview import PreviewResampler, relay_cloud_preview
from backend.adapters.detectif_adapter import DetectifHTTPClient, DetectifVoiceEvidenceAdapter
from backend.adapters.audio_decoder import AudioDecoder
from backend.models.turn import OriginalAudioMetadata


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(404, "SPEAKER_NOT_FOUND"), (401, "INVALID_CREDENTIAL"),
                                         (503, "ENROLLMENT_CHECK_UNAVAILABLE")])
async def test_preflight_blocks_paid_upload_and_uses_only_selected_key(status, code):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer combined-test"
        return httpx.Response(status, json={"error": {"code": "speaker_not_found"}})
    client = DetectifHTTPClient(api_key="legacy-test", speaker_api_key="speaker-test",
        deepfake_api_key="deepfake-test", combined_api_key="combined-test", transport=httpx.MockTransport(handler))
    adapter = DetectifVoiceEvidenceAdapter(client, account_alias="test")
    result = await adapter.preflight_speaker("emp_4002_arvind", "combined", "test")
    assert result.error_code == code
    assert result.credits_charged is None
    if status != 503:
        assert (await adapter.preflight_speaker("emp_4002_arvind", "combined", "test")).error_code == code
        assert len(requests) == 1  # Bounded negative cache avoids repeated lookups, too.
    await client.close()


@pytest.mark.asyncio
async def test_preflight_does_not_confuse_accounts_or_credentials():
    seen = []
    def handler(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200 if seen[-1] == "Bearer speaker-test" else 404, json={"speaker_id": "one"})
    client = DetectifHTTPClient(api_key=None, speaker_api_key="speaker-test", combined_api_key="combined-test",
        transport=httpx.MockTransport(handler))
    adapter = DetectifVoiceEvidenceAdapter(client, account_alias="test")
    assert await adapter.preflight_speaker("one", "speaker", "test") is None
    assert (await adapter.preflight_speaker("one", "combined", "test")).error_code == "SPEAKER_NOT_FOUND"
    assert (await adapter.preflight_speaker("one", "speaker", "other")).error_code == "ACCOUNT_MAPPING_MISMATCH"
    assert seen == ["Bearer speaker-test", "Bearer combined-test"]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("charge", [0, 50])
async def test_official_deepfake_envelope_and_exact_credit_amount(charge):
    def handler(request):
        assert request.url.path.endswith("/deepfake/detect")
        return httpx.Response(200, json={"result": {"verdict": "real", "score": 0.07, "threshold": 0.62},
            "model": {"name": "aletheia", "version": "test-version"},
            "idempotent_replay": charge == 0, "credits": {"charged": charge, "original_charge": 50}},
            headers={"x-credits-charged": "999"})
    wrapper = DetectifHTTPClient(api_key=None, deepfake_api_key="fake-deepfake", transport=httpx.MockTransport(handler))
    adapter = DetectifVoiceEvidenceAdapter(wrapper)
    audio = AudioDecoder.pcm_to_wav_bytes(np.ones(80000, dtype=np.float32) * 0.1, 16000)
    meta = OriginalAudioMetadata(safe_filename="test.wav", declared_content_type="audio/wav",
        normalized_mime_type="audio/wav", byte_count=len(audio), sha256_digest="test")
    result = await adapter.verify_evidence(meta, audio, None, "test-turn", mode="deepfake")
    assert result.deepfake_verdict == "real"
    assert result.deepfake_score == 0.07
    assert result.model_version == "test-version"
    assert result.credits_charged == charge
    assert result.is_idempotent_replay == (charge == 0)
    assert not result.is_dual_verified
    await wrapper.close()


@pytest.mark.asyncio
async def test_partial_combined_failure_records_charge_without_granting_access():
    def handler(_):
        return httpx.Response(404, json={"error": {"message": "speaker missing", "code": "speaker_not_found"},
            "credits": {"charged": 50}, "partial": {"verdict": "real", "score": 0.07}})
    wrapper = DetectifHTTPClient(api_key=None, combined_api_key="fake-combined", transport=httpx.MockTransport(handler))
    adapter = DetectifVoiceEvidenceAdapter(wrapper)
    audio = AudioDecoder.pcm_to_wav_bytes(np.ones(80000, dtype=np.float32) * 0.1, 16000)
    meta = OriginalAudioMetadata(safe_filename="test.wav", declared_content_type="audio/wav",
        normalized_mime_type="audio/wav", byte_count=len(audio), sha256_digest="test")
    result = await adapter.verify_evidence(meta, audio, "missing", "test-turn", mode="combined")
    assert result.error_code == "SPEAKER_NOT_FOUND"
    assert result.credits_charged == 50
    assert not result.is_dual_verified
    await wrapper.close()


def test_preview_resampling_is_independent_of_chunk_boundaries():
    source = (np.sin(np.arange(16000) * 0.13) * 20000).astype("<i2").tobytes()
    whole = PreviewResampler().append(source)
    stream = PreviewResampler()
    split = b"".join(stream.append(source[i:i + 2048]) for i in range(0, len(source), 2048))
    assert abs(len(split) - 48000) <= 4
    assert np.max(np.abs(np.frombuffer(whole, "<i2").astype(int) - np.frombuffer(split, "<i2"))) <= 1


@pytest.mark.parametrize("container_format,codec", [("webm", "libopus"), ("mp4", "aac")])
def test_browser_container_decoding_without_local_inference(container_format, codec):
    import av
    output = io.BytesIO()
    with av.open(output, "w", format=container_format) as container:
        stream = container.add_stream(codec, rate=48000)
        stream.layout = "mono"
        for start in range(0, 48000 * 5, 4800):
            wave = (np.sin(np.arange(start, start + 4800) * 2 * np.pi * 220 / 48000) * 0.2).astype(np.float32)[None, :]
            frame = av.AudioFrame.from_ndarray(wave, format="fltp", layout="mono")
            frame.sample_rate = 48000
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    pcm = AudioDecoder.decode_to_16k_mono(output.getvalue())
    assert 4.9 <= len(pcm) / 16000 <= 5.1
    assert np.isfinite(pcm).all()


class Browser:
    def __init__(self):
        self.sent = []
        self.messages = asyncio.Queue()
    async def send_json(self, payload):
        self.sent.append(payload)
        if payload["type"] == "ready":
            self.messages.put_nowait({"type": "websocket.receive", "bytes": b"\x01\x00" * 1024})
        elif payload["type"] == "transcript.partial":
            self.messages.put_nowait({"type": "websocket.disconnect"})
    async def receive(self):
        return await self.messages.get()


class Upstream:
    def __init__(self, reject=False):
        self.sent = []
        self.events = asyncio.Queue()
        self.events.put_nowait(json.dumps({"type": "error" if reject else "session.updated"}))
        self.closed = False
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        self.closed = True
    async def send(self, payload):
        event = json.loads(payload)
        self.sent.append(event)
        if event["type"] == "input_audio_buffer.append":
            self.events.put_nowait(json.dumps({"type": "conversation.item.input_audio_transcription.delta", "delta": "My employee ID"}))
    async def recv(self):
        return await self.events.get()
    def __aiter__(self):
        return self
    async def __anext__(self):
        return await self.recv()


@pytest.mark.asyncio
async def test_cloud_stream_emits_live_partial_without_final_or_biometric_call():
    browser, upstream = Browser(), Upstream()
    connections = []
    def connector(url, **kwargs):
        connections.append((url, kwargs))
        return upstream
    await relay_cloud_preview(browser, SimpleNamespace(api_key="fake-server-key"),
        SimpleNamespace(OPENAI_PREVIEW_MODEL="gpt-live-transcribe"), connector=connector)
    assert len(connections) == 1
    assert upstream.closed
    assert browser.sent[-1] == {"type": "transcript.partial", "text": "My employee ID"}
    assert upstream.sent[0]["session"]["type"] == "transcription"
    assert upstream.sent[0]["session"]["audio"]["input"]["turn_detection"] is None
    assert "fake-server-key" not in json.dumps(browser.sent)


@pytest.mark.asyncio
async def test_rejected_cloud_configuration_never_claims_ready_or_retries():
    browser, upstream = Browser(), Upstream(reject=True)
    calls = []
    def connector(*args, **kwargs):
        calls.append(1)
        return upstream
    await relay_cloud_preview(browser, SimpleNamespace(api_key="fake-server-key"),
        SimpleNamespace(OPENAI_PREVIEW_MODEL="gpt-live-transcribe"), connector=connector)
    assert calls == [1]
    assert [e["type"] for e in browser.sent] == ["unavailable"]
    assert "pause" in browser.sent[0]["message"]
