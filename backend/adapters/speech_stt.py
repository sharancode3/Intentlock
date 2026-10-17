"""
IntentLock — Faster-Whisper Speech-to-Text (STT) Adapter
Implements SpeechInputPort contract using CTranslate2 int8 Faster-Whisper on CPU.
Reuses upstream Faster-Whisper integration patterns from speech_hf/src/speech_to_speech/STT.
"""

import os
import sys
import time
import pathlib
import logging
import threading
from typing import Optional
import numpy as np
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

from backend.core.ports import SpeechInputPort, SpeechInputResult
from backend.models.turn import OriginalAudioMetadata
from backend.adapters.audio_decoder import AudioDecoder
from backend.adapters.speech_vad import SpeechVADService, VADSpeechReport

logger = logging.getLogger("intentlock.stt")


class FasterWhisperSTTAdapter(SpeechInputPort):
    """Production Faster-Whisper STT adapter on CPU int8."""

    def __init__(
        self,
        model_name: str = "tiny.en",
        device: str = "cpu",
        compute_type: str = "int8",
        vad_service: Optional[SpeechVADService] = None,
    ):
        if WhisperModel is None:
            raise RuntimeError("The 'faster-whisper' package is not installed. FasterWhisperSTTAdapter cannot initialize.")
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.vad_service = vad_service or SpeechVADService.get_instance()
        self._is_ready = False
        self._inference_lock = threading.Lock()

        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        logger.info(f"Loading Faster-Whisper STT model: {model_name} on {device} ({compute_type})...")
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        logger.info("Faster-Whisper model loaded successfully.")

    def warmup(self) -> None:
        """Warms up the STT inference pipeline with a short dummy audio buffer."""
        try:
            logger.info("Warming up Faster-Whisper STT...")
            dummy_pcm = np.zeros(8000, dtype=np.float32)  # 0.5s silence
            segments, _ = self.model.transcribe(dummy_pcm, beam_size=1)
            list(segments)  # actually consume the segment generator
            self._is_ready = True
            logger.info("Faster-Whisper STT warmed up and ready.")
        except Exception as e:
            logger.error(f"STT warmup failed: {e}")
            self._is_ready = False

    def is_ready(self) -> bool:
        return self._is_ready

    def _sync_transcribe(self, audio_bytes: bytes) -> tuple[Optional[str], Optional[str], Optional[float], Optional[float]]:
        """Synchronous CPU execution of decoding, VAD, and Whisper inference."""
        # Step 1: Decode audio
        try:
            audio_16k = AudioDecoder.decode_to_16k_mono(audio_bytes, max_duration_s=60.0, min_duration_s=0.1)
        except ValueError as ve:
            return None, f"DECODE_ERROR: {str(ve)}", None, None

        # Step 2: VAD verification
        vad_report: VADSpeechReport = self.vad_service.validate_speech(audio_16k)
        if not vad_report.has_speech:
            return "", "NO_SPEECH_DETECTED", None, vad_report.speech_duration_s

        # Step 3: Run Faster-Whisper
        try:
            segments, info = self.model.transcribe(
                audio_16k,
                beam_size=1,
                language="en",
                condition_on_previous_text=False,
            )
            transcribed_chunks = [seg.text.strip() for seg in segments if seg.text.strip()]
            final_transcript = " ".join(transcribed_chunks).strip()
            return final_transcript, None, getattr(info, "language_probability", None), vad_report.speech_duration_s
        except Exception as e:
            return None, f"TRANSCRIPTION_ERROR: {str(e)}", None, vad_report.speech_duration_s

    async def transcribe(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        client_turn_id: str,
    ) -> SpeechInputResult:
        """
        Transcribe incoming audio bytes into text asynchronously without blocking the event loop.
        """
        import asyncio

        t0 = time.perf_counter()
        def run_serialized():
            with self._inference_lock:
                return self._sync_transcribe(audio_bytes)
        transcript, error_message, _lang_prob, speech_duration_s = await asyncio.to_thread(run_serialized)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if error_message:
            if error_message == "NO_SPEECH_DETECTED":
                logger.info(f"VAD filtered silence for turn={client_turn_id} in {latency_ms:.1f}ms")
                return SpeechInputResult(
                    is_available=True,
                    transcript="",
                    confidence=0.0,
                    latency_ms=round(latency_ms, 2),
                    error_message=error_message,
                )
            logger.error(f"STT failed for turn={client_turn_id}: {error_message}")
            return SpeechInputResult(
                is_available=True,
                transcript=None,
                confidence=None,
                latency_ms=round(latency_ms, 2),
                error_message=error_message,
            )

        # Do not log raw transcript at INFO level for privacy
        logger.info(f"STT completed for turn={client_turn_id} in {latency_ms:.1f}ms (length={len(transcript or '')})")
        logger.debug(f"Turn={client_turn_id} transcript: {transcript}")

        return SpeechInputResult(
            is_available=True,
            transcript=transcript,
            confidence=None,  # Do not mislabel language probability as transcription confidence
            latency_ms=round(latency_ms, 2),
            error_message=None,
            speech_duration_s=speech_duration_s,
        )

    def cleanup(self) -> None:
        logger.info("Cleaning up Faster-Whisper model.")
        if hasattr(self, "model"):
            del self.model


class OpenAISpeechInputAdapter(SpeechInputPort):
    """Cloud Speech-to-Text adapter using OpenAI Whisper API (whisper-1).

    Provides studio-grade transcription with zero local RAM footprint,
    eliminating low-memory deployment OOM crashes on platforms like Render (512MB limit).
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1"):
        from backend.core.config import settings
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = getattr(settings, "OPENAI_API_KEY", None)
        self.model = model
        self.is_available = bool(self.api_key)
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def transcribe(
        self,
        audio_metadata: OriginalAudioMetadata,
        audio_bytes: bytes,
        client_turn_id: str,
    ) -> SpeechInputResult:
        if not self.is_available or not self.api_key:
            return SpeechInputResult(
                is_available=False,
                error_message="OpenAI API key not configured for STT",
            )

        t0 = time.perf_counter()
        try:
            client = self._get_client()
            mime_type = getattr(audio_metadata, "normalized_mime_type", None) or getattr(audio_metadata, "mime_type", "audio/wav")
            ext = "wav"
            if "webm" in mime_type:
                ext = "webm"
            elif "ogg" in mime_type:
                ext = "ogg"
            elif "mp4" in mime_type or "m4a" in mime_type:
                ext = "m4a"
            filename = f"audio_{client_turn_id}.{ext}"

            response = await client.audio.transcriptions.create(
                model=self.model,
                file=(filename, audio_bytes, mime_type),
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            transcript = (response.text or "").strip()
            duration_ms = getattr(audio_metadata, "duration_ms", None)
            speech_duration_s = (duration_ms / 1000.0) if duration_ms is not None else None

            logger.info(f"OpenAI STT completed for turn={client_turn_id} in {latency_ms:.1f}ms (length={len(transcript)})")
            return SpeechInputResult(
                is_available=True,
                transcript=transcript,
                confidence=0.98,
                latency_ms=round(latency_ms, 2),
                error_message=None,
                speech_duration_s=speech_duration_s,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(f"OpenAI STT failed for turn={client_turn_id}: {e}")
            return SpeechInputResult(
                is_available=False,
                error_message=str(e),
                latency_ms=round(latency_ms, 2),
            )

    def cleanup(self) -> None:
        self._client = None
