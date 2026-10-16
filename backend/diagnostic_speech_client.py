"""IntentLock — Backend Diagnostic Speech Client.

This diagnostic client allows developers and teammates to verify the end-to-end
speech pipeline (VAD, Faster-Whisper STT, Kokoro-82M TTS) against the running
IntentLock FastAPI backend without requiring a browser UI.

Note:
    - This is a diagnostic utility for backend validation only.
    - It does not bypass identity policies or grant access to private records.
    - If Detectif is unconfigured, the turn remains ANONYMOUS and private records remain blocked.
    - Chat UI integration in the browser frontend is owned by the frontend workstream.
"""

import argparse
import base64
import json
import os
import sys
import time
import uuid
import wave
import io
import requests

DEFAULT_SERVER_URL = os.getenv("INTENTLOCK_SERVER_URL", "http://127.0.0.1:8000")


def generate_synthetic_audio_wav(duration_s: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate a simple sine tone WAV for connectivity/latency test."""
    import math
    import struct

    buf = io.BytesIO()
    num_samples = int(duration_s * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # 440Hz tone
        for i in range(num_samples):
            val = int(16000.0 * math.sin(2.0 * math.pi * 440.0 * (i / sample_rate)))
            buf_data = struct.pack("<h", val)
            wf.writeframes(buf_data)
    return buf.getvalue()


def run_diagnostic_turn(
    server_url: str,
    audio_path: str | None = None,
    output_wav: str | None = "diagnostic_response.wav",
    client_turn_id: str | None = None,
) -> None:
    server_url = server_url.rstrip("/")
    turn_id = client_turn_id or str(uuid.uuid4())

    print("=================================================================")
    print("   IntentLock Speech Pipeline Diagnostic Client")
    print("=================================================================")
    print(f"Target Server : {server_url}")
    print(f"Client Turn ID: {turn_id}")

    # 1. Health and Readiness Check
    print("\n[Step 1] Checking server health and readiness...")
    try:
        health_resp = requests.get(f"{server_url}/health/live", timeout=5)
        print(f"  GET /health/live status: {health_resp.status_code}")
        ready_resp = requests.get(f"{server_url}/health/ready", timeout=5)
        print(f"  GET /health/ready status: {ready_resp.status_code}")
        ready_data = ready_resp.json()
        speech_comp_status = ready_data.get("components", {}).get("speech_service", "unknown")
        print(f"  Components:")
        for comp, status in ready_data.get("components", {}).items():
            print(f"    - {comp}: {status}")
        if speech_comp_status != "ready":
            print(f"  [WARN] Speech service is reported as '{speech_comp_status}'. Continuing test...")
        else:
            print("  [OK] Speech service is warmed up and reported READY.")
    except Exception as exc:
        print(f"  [ERROR] Failed to reach server health probe: {exc}")
        sys.exit(1)

    # 2. Prepare Audio
    print("\n[Step 2] Preparing audio input payload...")
    mime_type = "audio/wav"
    if audio_path and os.path.exists(audio_path):
        print(f"  Reading provided audio file: {audio_path}")
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        if audio_path.endswith(".webm"):
            mime_type = "audio/webm"
        elif audio_path.endswith(".mp4") or audio_path.endswith(".m4a"):
            mime_type = "audio/mp4"
    else:
        print("  Generating test synthetic audio tone (16kHz PCM mono WAV)...")
        audio_bytes = generate_synthetic_audio_wav(duration_s=2.0, sample_rate=16000)

    print(f"  Audio payload size: {len(audio_bytes)} bytes (MIME: {mime_type})")

    # 3. Submit Voice Turn
    print("\n[Step 3] Submitting POST /api/v1/voice/turn...")
    start_time = time.monotonic()
    files = {
        "audio_file": ("test_turn.wav", audio_bytes, mime_type),
    }
    data = {
        "client_turn_id": turn_id,
        "client_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        resp = requests.post(f"{server_url}/api/v1/voice/turn", files=files, data=data, timeout=30)
        round_trip_ms = round((time.monotonic() - start_time) * 1000, 2)
        print(f"  HTTP Response: {resp.status_code} ({round_trip_ms} ms round-trip)")

        if resp.status_code == 200:
            result = resp.json()
            print("\n[Step 4] Turn Results:")
            print(f"  Status             : {result.get('status')}")
            print(f"  Session Identity   : {result.get('session_id', 'None')}")
            print(f"  Recognized Text    : \"{result.get('transcript', '')}\"")
            print(f"  Spoken Summary     : \"{result.get('spoken_summary', '')}\"")
            
            timings = result.get("speech_timings_ms") or {}
            print(f"  Speech Timings (ms):")
            for k, v in timings.items():
                print(f"    - {k}: {v} ms")

            # Check TTS audio payload
            speech_audio = result.get("speech_audio")
            if speech_audio and speech_audio.get("base64_audio"):
                audio_b64 = speech_audio["base64_audio"]
                audio_raw = base64.b64decode(audio_b64)
                print(f"\n[Step 5] Synthesized Audio Received:")
                print(f"  MIME Type   : {speech_audio.get('mime_type')}")
                print(f"  Sample Rate : {speech_audio.get('sample_rate')} Hz")
                print(f"  Channels    : {speech_audio.get('channels')}")
                print(f"  Bytes       : {len(audio_raw)} bytes ({speech_audio.get('byte_count')} reported)")
                print(f"  Duration    : {speech_audio.get('duration_ms')} ms")

                if output_wav:
                    with open(output_wav, "wb") as out_f:
                        out_f.write(audio_raw)
                    print(f"  Saved response WAV to: {os.path.abspath(output_wav)}")
            else:
                print("\n[Step 5] No synthesized audio payload returned in response.")
            
            print("\n[SUCCESS] Speech turn completed successfully via backend pipeline.")

        elif resp.status_code == 400:
            print(f"  Turn rejected (expected for silence/corrupt audio): {resp.text}")
        elif resp.status_code == 503:
            print(f"  Speech pipeline unavailable: {resp.text}")
        else:
            print(f"  Unexpected response [{resp.status_code}]: {resp.text}")

    except Exception as exc:
        print(f"  [ERROR] Turn request failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IntentLock Speech Pipeline Diagnostic Client")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="Base URL of IntentLock server")
    parser.add_argument("--audio", default=None, help="Path to input audio file (WAV/WebM/MP4)")
    parser.add_argument("--out", default="diagnostic_response.wav", help="Path to save output synthesized WAV")
    args = parser.parse_args()

    run_diagnostic_turn(server_url=args.url, audio_path=args.audio, output_wav=args.out)
