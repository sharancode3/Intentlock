"""Opt-in local VAD/STT WebSocket smoke test using generated speech, no paid APIs.

Run after starting backend.main on port 8000:
    python -B -m backend.diagnostic_preview_client
This tests the preview transport and models, not real microphone or Detectif accuracy.
"""
import asyncio
import json
import numpy as np
import websockets
from backend.adapters.speech_tts import KokoroTTSAdapter
from backend.adapters.audio_decoder import AudioDecoder


async def main():
    tts = KokoroTTSAdapter()
    generated = await tts.synthesize(
        "Please show my employee profile and tell me about my current company projects.", "preview-smoke"
    )
    assert generated.audio_bytes, "Local TTS failed"
    samples = AudioDecoder.decode_to_16k_mono(generated.audio_bytes)
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes() + bytes(32000 * 3)
    events = []
    async with websockets.connect('ws://127.0.0.1:8000/api/v1/voice/preview', origin='http://localhost:5173') as ws:
        assert json.loads(await ws.recv())['type'] == 'ready'

        async def receive():
            async for message in ws:
                events.append(json.loads(message))

        receiver = asyncio.create_task(receive())
        for pos in range(0, len(pcm), 2048):
            await ws.send(pcm[pos:pos+2048])
            await asyncio.sleep(0.064)
        await asyncio.sleep(1)
        receiver.cancel()
        try:
            await receiver
        except asyncio.CancelledError:
            pass
    partials = [e for e in events if e['type'] == 'transcript.partial']
    voiced = any(e['type'] == 'vad' and e['speech'] for e in events)
    silence = any(e['type'] == 'vad' and not e['speech'] for e in events)
    print(json.dumps({'generated_audio_seconds': round(len(samples) / 16000, 2),
                      'partial_count': len(partials), 'speech_detected': voiced,
                      'silence_detected': silence,
                      'last_partial': partials[-1]['text'] if partials else None}))
    assert partials and voiced and silence, 'Preview did not produce the expected local speech events'


if __name__ == '__main__':
    asyncio.run(main())
