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
KPipeline = None  # Cloud TTS must not import local Torch/Kokoro runtimes.

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
        global KPipeline
        if KPipeline is None:
            from kokoro import KPipeline
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


class OpenAISpeechOutputAdapter(SpeechOutputPort):
    """Cloud Text-to-Speech adapter using OpenAI TTS API (tts-1).

    Provides high-fidelity 24kHz neural voice synthesis with zero local RAM footprint,
    eliminating low-memory deployment OOM crashes on platforms like Render (512MB limit).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "tts-1",
        voice: str = "alloy",
    ):
        from backend.core.config import settings
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = getattr(settings, "OPENAI_API_KEY", None)
        self.model = model
        self.voice = voice or getattr(settings, "OPENAI_TTS_VOICE", "alloy")
        self.is_available = bool(self.api_key)
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            from openai import AsyncOpenAI
            from backend.core.config import settings
            self._client = AsyncOpenAI(api_key=self.api_key,
                timeout=settings.OPENAI_TIMEOUT_SECONDS, max_retries=settings.OPENAI_MAX_RETRIES)
        return self._client

    async def synthesize(
        self,
        text: str,
        client_turn_id: str,
    ) -> SpeechOutputResult:
        if not self.is_available or not self.api_key:
            return SpeechOutputResult(
                is_available=False,
                error_message="OpenAI API key not configured for TTS",
            )

        if not text or not text.strip():
            return SpeechOutputResult(
                is_available=True,
                audio_bytes=None,
                audio_format=None,
                latency_ms=0.0,
                error_message="EMPTY_TEXT",
            )

        t0 = time.perf_counter()
        try:
            client = self._get_client()
            response = await client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text.strip(),
                response_format="wav",
            )
            audio_bytes = response.content
            latency_ms = (time.perf_counter() - t0) * 1000.0

            logger.info(
                f"OpenAI TTS synthesized {len(text)} chars into {len(audio_bytes)} WAV bytes "
                f"for turn={client_turn_id} in {latency_ms:.1f}ms"
            )
            return SpeechOutputResult(
                is_available=True,
                audio_bytes=audio_bytes,
                audio_format="audio/wav",
                latency_ms=round(latency_ms, 2),
                error_message=None,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(f"OpenAI TTS failed for turn={client_turn_id}: {e}")
            return SpeechOutputResult(
                is_available=False,
                error_message=str(e),
                latency_ms=round(latency_ms, 2),
            )

    def cleanup(self) -> None:
        self._client = None
