"""
IntentLock — Test Speech Service
Integrates Faster-Whisper (STT) and Kokoro (neural TTS) for the local
post-verification render-test workspace.

Features:
- PyAV container decoding (WebM/Opus, MP4, WAV, OGG -> 16kHz float32 mono).
- Faster-Whisper STT with Silero VAD filtering.
- Kokoro ONNX neural TTS synthesizing natural English speech at 24kHz.
- Thread-safe singleton model holders.
"""

import os
import io
import re
import logging
import threading
from typing import Tuple, Optional
import numpy as np
import av
import soundfile as sf
from faster_whisper import WhisperModel

logger = logging.getLogger("test_speech_service")

# Model paths
CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models_cache"))
KOKORO_MODEL_PATH = os.path.join(CACHE_DIR, "kokoro-v0_19.onnx")
KOKORO_VOICES_PATH = os.path.join(CACHE_DIR, "voices.bin")

_whisper_lock = threading.Lock()
_kokoro_lock = threading.Lock()
_whisper_instance: Optional[WhisperModel] = None
_kokoro_instance = None

def get_whisper_model() -> WhisperModel:
    global _whisper_instance
    if _whisper_instance is None:
        with _whisper_lock:
            if _whisper_instance is None:
                logger.info("Initializing Faster-Whisper (tiny.en, CPU, INT8)...")
                _whisper_instance = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                logger.info("Faster-Whisper initialized successfully.")
    return _whisper_instance

def get_kokoro_model():
    global _kokoro_instance
    if _kokoro_instance is None:
        with _kokoro_lock:
            if _kokoro_instance is None:
                if os.path.exists(KOKORO_MODEL_PATH) and os.path.exists(KOKORO_VOICES_PATH):
                    try:
                        import kokoro_onnx
                        logger.info(f"Initializing Kokoro ONNX TTS from {KOKORO_MODEL_PATH}...")
                        _kokoro_instance = kokoro_onnx.Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
                        logger.info("Kokoro ONNX TTS initialized successfully.")
                    except Exception as e:
                        logger.warning(f"Failed to load Kokoro ONNX: {e}")
                        _kokoro_instance = None
                else:
                    logger.warning("Kokoro ONNX model files not found in cache.")
    return _kokoro_instance

def decode_audio_bytes(audio_bytes: bytes) -> np.ndarray:
    """
    Decodes arbitrary audio container bytes (WebM, WAV, MP4, OGG)
    into a mono 16kHz float32 numpy array.
    """
    if not audio_bytes or len(audio_bytes) < 32:
        return np.zeros(0, dtype=np.float32)

    buf = io.BytesIO(audio_bytes)
    try:
        container = av.open(buf)
    except Exception as e:
        logger.error(f"PyAV failed to open container: {e}")
        return np.zeros(0, dtype=np.float32)

    if not container.streams.audio:
        logger.error("No audio stream found in container.")
        return np.zeros(0, dtype=np.float32)

    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)

    pcm_chunks = []
    try:
        for frame in container.decode(stream):
            for r_frame in resampler.resample(frame):
                pcm_chunks.append(r_frame.to_ndarray().flatten())
    except Exception as e:
        logger.warning(f"Error during audio packet decoding: {e}")

    if not pcm_chunks:
        return np.zeros(0, dtype=np.float32)

    audio = np.concatenate(pcm_chunks).astype(np.float32)
    return audio

def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """
    Transcribes audio bytes to text using Faster-Whisper with Silero VAD filtering.
    """
    audio = decode_audio_bytes(audio_bytes)
    if len(audio) < 1600:  # less than 0.1s
        logger.info("Audio duration too short for transcription.")
        return ""

    model = get_whisper_model()
    segments, info = model.transcribe(
        audio,
        language="en",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
    )

    text_parts = [segment.text.strip() for segment in segments]
    full_transcript = " ".join(text_parts).strip()
    logger.info(f"Transcription complete: '{full_transcript}'")
    return full_transcript

def clean_text_for_speech(text: str) -> str:
    """
    Strips markdown formatting, URLs, and code blocks for clean neural speech synthesis.
    """
    # Remove code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove markdown links, keep anchor text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove bold, italics, bullets, hashtags
    text = re.sub(r"[*_#`~>|-]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Limit length for speech if too long (first 2-3 sentences)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 4:
        text = " ".join(sentences[:4])
    return text

def synthesize_speech(text: str, voice: str = "af_sarah") -> Tuple[bytes, str]:
    """
    Synthesizes text into 24kHz WAV audio using Kokoro ONNX.
    Falls back gracefully to a clean tone/silence if model unavailable.
    Returns (wav_bytes, 'audio/wav').
    """
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        clean_text = "No response text available."

    kokoro = get_kokoro_model()
    if kokoro is not None:
        try:
            samples, sample_rate = kokoro.create(clean_text, voice=voice, speed=1.0, lang="en-us")
            out_buf = io.BytesIO()
            sf.write(out_buf, samples, sample_rate, format="WAV")
            out_buf.seek(0)
            return out_buf.read(), "audio/wav"
        except Exception as e:
            logger.error(f"Kokoro synthesis failed: {e}")

    # Fallback synthesizer: produces a clean speech-notification tone
    sample_rate = 24000
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Gentle chime (A4 + E5 harmonic fade)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 659.25 * t)) * np.exp(-3 * t)
    out_buf = io.BytesIO()
    sf.write(out_buf, tone.astype(np.float32), sample_rate, format="WAV")
    out_buf.seek(0)
    return out_buf.read(), "audio/wav"
