"""
IntentLock — Kokoro Text-to-Speech (TTS) Adapter
Implements SpeechOutputPort contract using native Kokoro-82M model on CPU.
Reuses upstream Kokoro integration patterns from speech_hf/src/speech_to_speech/TTS/kokoro_handler.py.
"""

import sys
import time
import pathlib
import logging
from typing import Optional
import numpy as np
from kokoro import KPipeline

from backend.core.ports import SpeechOutputPort, SpeechOutputResult
from backend.adapters.audio_decoder import AudioDecoder

logger = logging.getLogger("intentlock.tts")


class KokoroTTSAdapter(SpeechOutputPort):
    """Production Kokoro-82M TTS adapter on CPU."""

    def __init__(
        self,
        lang_code: str = "a",
        voice: str = "af_heart",
        speed: float = 1.0,
        device: str = "cpu",
    ):
        self.lang_code = lang_code
        self.voice = voice
        self.speed = speed
        self.device = device
        self._is_ready = False

        logger.info(f"Loading Kokoro TTS pipeline: lang={lang_code}, voice={voice} on {device}...")
        self.pipeline = KPipeline(lang_code=lang_code, device=device)
        logger.info("Kokoro TTS pipeline loaded successfully.")

    def warmup(self) -> None:
        """Warms up the TTS synthesis pipeline with a short dummy phrase."""
        try:
            logger.info("Warming up Kokoro TTS...")
            for _ in self.pipeline("Hello", voice=self.voice, speed=self.speed):
                pass
            self._is_ready = True
            logger.info("Kokoro TTS warmed up and ready.")
        except Exception as e:
            logger.error(f"TTS warmup failed: {e}")
            self._is_ready = False

    def is_ready(self) -> bool:
        return self._is_ready

    def _sync_synthesize(self, clean_text: str) -> tuple[Optional[bytes], Optional[str]]:
        """Synchronous CPU execution of Kokoro text-to-speech synthesis."""
        try:
            generator = self.pipeline(clean_text, voice=self.voice, speed=self.speed)
            audio_segments = []

            for chunk in generator:
                audio_tensor = chunk.audio
                if audio_tensor is not None:
                    audio_segments.append(audio_tensor.cpu().numpy())

            if not audio_segments:
                return None, "NO_AUDIO_GENERATED"

            # Concatenate chunks into 1D float32 array
            concatenated = np.concatenate(audio_segments, axis=0)

            # Convert to 24kHz 16-bit mono WAV container
            wav_bytes = AudioDecoder.pcm_to_wav_bytes(concatenated, sample_rate=24000)
            return wav_bytes, None
        except Exception as e:
            return None, f"SYNTHESIS_ERROR: {str(e)}"

    async def synthesize(
        self,
        text: str,
        client_turn_id: str,
    ) -> SpeechOutputResult:
        """
        Synthesize backend-approved plain text into 24kHz 16-bit mono WAV bytes
        asynchronously without blocking the event loop.
        """
        import asyncio

        t0 = time.perf_counter()

        clean_text = text.strip() if text else ""
        if not clean_text:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return SpeechOutputResult(
                is_available=True,
                audio_bytes=None,
                audio_format=None,
                latency_ms=round(latency_ms, 2),
                error_message="EMPTY_TEXT",
            )

        wav_bytes, error_message = await asyncio.to_thread(self._sync_synthesize, clean_text)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if error_message:
            logger.error(f"TTS synthesis failed for turn={client_turn_id}: {error_message}")
            return SpeechOutputResult(
                is_available=True,
                audio_bytes=None,
                audio_format=None,
                latency_ms=round(latency_ms, 2),
                error_message=error_message,
            )

        logger.info(
            f"TTS synthesized {len(clean_text)} chars into {len(wav_bytes or b'')} WAV bytes "
            f"for turn={client_turn_id} in {latency_ms:.1f}ms"
        )

        return SpeechOutputResult(
            is_available=True,
            audio_bytes=wav_bytes,
            audio_format="audio/wav",
            latency_ms=round(latency_ms, 2),
            error_message=None,
        )

    def cleanup(self) -> None:
        logger.info("Cleaning up Kokoro TTS pipeline.")
        if hasattr(self, "pipeline"):
            del self.pipeline
