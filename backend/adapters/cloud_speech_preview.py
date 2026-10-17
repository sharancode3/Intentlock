"""Bounded OpenAI transcription relay. Preview text never grants identity or access.

One upstream stream per utterance; no LLM, Detectif call, batch re-transcription,
automatic reconnect, or database access. The original recording uses the final gateway.
"""
import asyncio
import base64
import contextlib
import json
import logging

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

logger = logging.getLogger("intentlock.speech_preview")


class PreviewResampler:
    """Streaming 16k -> 24k PCM16 interpolation; retain phase across frame boundaries."""
    def __init__(self):
        self.pending = np.empty(0, dtype=np.float32)
        self.position = 0.0

    def append(self, chunk: bytes) -> bytes:
        self.pending = np.concatenate((self.pending, np.frombuffer(chunk, dtype="<i2")))
        positions = np.arange(self.position, len(self.pending) - 1, 2 / 3)
        if not len(positions):
            return b""
        output = np.interp(positions, np.arange(len(self.pending)), self.pending)
        self.position = float(positions[-1] + 2 / 3)
        consumed = int(self.position)
        self.pending = self.pending[consumed:]
        self.position -= consumed
        return np.rint(output).astype("<i2").tobytes()


async def relay_cloud_preview(ws: WebSocket, stt, settings, *, connector=connect):
    tasks = []
    try:
        async with connector(
            "wss://api.openai.com/v1/realtime?intent=transcription",
            additional_headers={"Authorization": f"Bearer {stt.api_key}"},
            open_timeout=6, close_timeout=1, max_size=65536, max_queue=8,
        ) as upstream:
            await upstream.send(json.dumps({
                "type": "session.update", "session": {
                    "type": "transcription", "audio": {"input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "transcription": {"model": settings.OPENAI_PREVIEW_MODEL},
                        "turn_detection": None,
                    }},
                },
            }))
            # Do not advertise live preview before the provider accepts its configuration.
            async def configure():
                while True:
                    event = json.loads(await upstream.recv())
                    if event.get("type") == "session.updated":
                        break
                    if event.get("type") == "error":
                        raise RuntimeError("Preview configuration rejected")
            await asyncio.wait_for(configure(), timeout=6)
            await ws.send_json({"type": "ready", "sample_rate": 16000,
                                "encoding": "pcm_s16le", "max_utterance_seconds": 55})

            async def upload():
                resampler = PreviewResampler()
                total = 0
                while True:
                    message = await asyncio.wait_for(ws.receive(), timeout=22)
                    if message["type"] == "websocket.disconnect":
                        return
                    chunk = message.get("bytes")
                    if not chunk or len(chunk) % 2 or len(chunk) > 16384:
                        await ws.close(code=1008, reason="Expected bounded mono PCM16 frames")
                        return
                    total += len(chunk)
                    if total > 55 * 32000:
                        await ws.send_json({"type": "limit"})
                        return
                    pcm = resampler.append(chunk)
                    await upstream.send(json.dumps({"type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm).decode("ascii")}))

            async def receive():
                text = ""
                async for raw in upstream:
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "error" or kind == "conversation.item.input_audio_transcription.failed":
                        raise RuntimeError("Preview transcription unavailable")
                    if kind == "conversation.item.input_audio_transcription.delta":
                        text += event.get("delta", "")
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        text = event.get("transcript", "")
                    else:
                        continue
                    if len(text) > 4096:
                        raise RuntimeError("Preview text limit exceeded")
                    if text:
                        await ws.send_json({"type": "transcript.partial", "text": text})

            tasks = [asyncio.create_task(upload()), asyncio.create_task(receive())]
            done, _ = await asyncio.wait(tasks, timeout=65, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
    except (WebSocketDisconnect, asyncio.CancelledError):
        raise
    except Exception as exc:
        # Never expose upstream headers, credentials, or audio in browser/log output.
        logger.warning("Cloud speech preview unavailable (%s)", type(exc).__name__)
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.send_json({"type": "unavailable", "message":
                "Live transcript unavailable · pause still sends your recording for final transcription."})
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
