"""Bounded local speech preview. Never authenticates, retrieves records or calls providers.

The browser sends 16 kHz mono signed little-endian PCM for local VAD/ASR only.
The separate final HTTP turn still verifies the original MediaRecorder container.
"""
import asyncio
import contextlib
import hashlib
import time
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from backend.adapters.audio_decoder import AudioDecoder
from backend.models.turn import OriginalAudioMetadata


def register_voice_preview(app, settings, get_stt, get_vad):
    active_connections = 0

    @app.websocket(f"{settings.API_V1_PREFIX}/voice/preview")
    async def preview(ws: WebSocket):
        nonlocal active_connections
        # CORS middleware does not protect WebSockets.
        if ws.headers.get("origin") not in settings.FRONTEND_ORIGINS:
            await ws.close(code=1008)
            return
        if active_connections >= 2:
            await ws.close(code=1013)
            return
        await ws.accept()
        stt, vad = get_stt(), get_vad()
        if vad is None or not getattr(stt, "is_ready", lambda: False)():
            await ws.send_json({"type": "unavailable", "message": "Live speech preview is unavailable. You can still record and submit manually."})
            await ws.close(code=1013)
            return
        active_connections += 1
        audio = bytearray()
        max_bytes = 55 * 16000 * 2
        send_lock = asyncio.Lock()
        partial_task = None
        last_vad_samples = 0
        last_partial_samples = 0
        started = time.monotonic()

        async def send(payload):
            async with send_lock:
                await ws.send_json(payload)

        async def partial(snapshot):
            wav = AudioDecoder.pcm_to_wav_bytes(
                np.frombuffer(snapshot, dtype="<i2").astype(np.float32) / 32768.0, 16000
            )
            meta = OriginalAudioMetadata(
                safe_filename="preview.wav", declared_content_type="audio/wav",
                normalized_mime_type="audio/wav", byte_count=len(wav),
                sha256_digest=hashlib.sha256(wav).hexdigest(),
            )
            try:
                result = await stt.transcribe(meta, wav, "local-preview")
                if result.transcript:
                    await send({"type": "transcript.partial", "text": result.transcript,
                                "audio_seconds": len(snapshot) / 32000.0})
            except (WebSocketDisconnect, RuntimeError):
                pass

        try:
            await send({"type": "ready", "sample_rate": 16000,
                        "encoding": "pcm_s16le", "max_utterance_seconds": 55})
            while time.monotonic() - started < 90:
                message = await asyncio.wait_for(ws.receive(), timeout=25)
                if message["type"] == "websocket.disconnect":
                    break
                chunk = message.get("bytes")
                if chunk is None or not chunk or len(chunk) % 2 or len(chunk) > 16384:
                    await ws.close(code=1008, reason="Expected bounded mono PCM16 frames")
                    break
                if len(audio) + len(chunk) > max_bytes:
                    await send({"type": "limit", "message": "Please finish this utterance."})
                    break
                audio.extend(chunk)
                count = len(audio) // 2
                if count - last_vad_samples >= 5120:
                    last_vad_samples = count
                    # Analyze a rolling window, not each compressed MediaRecorder chunk.
                    window = np.frombuffer(bytes(audio[-48000:]), dtype="<i2").astype(np.float32) / 32768.0
                    report = await asyncio.to_thread(vad.validate_speech, window)
                    speech = bool(report.has_speech and report.offset_s is not None
                                  and report.offset_s >= len(window) / 16000.0 - 0.35)
                    await send({"type": "vad", "speech": speech})
                    if (speech and count >= 16000 and count - last_partial_samples >= 24000
                            and (partial_task is None or partial_task.done())):
                        if partial_task is not None:
                            # Retrieve exceptions so a broken client cannot leak task warnings.
                            partial_task.result()
                        last_partial_samples = count
                        partial_task = asyncio.create_task(partial(bytes(audio)))
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            pass
        finally:
            if partial_task is not None:
                # Cancelling to_thread cannot stop CPU inference; the model's lock bounds it.
                partial_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await partial_task
            audio.clear()
            active_connections -= 1
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await ws.close()
