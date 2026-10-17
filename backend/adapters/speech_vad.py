"""
IntentLock — Voice Activity Detection (VAD) Adapter
Integrates Silero VAD for:
1. Post-upload speech segmentation & silence rejection.
2. Real-time streaming turn boundary detection wrapping upstream VADIterator
   from speech_hf/src/speech_to_speech/VAD/vad_iterator.py.
"""

import sys
import pathlib
import logging
import threading
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
torch = None  # Local-only runtime; importing the cloud gateway must stay lightweight.
import numpy as np

# Ensure upstream speech_hf/src is on sys.path for direct component reuse
_UPSTREAM_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "speech_hf" / "src"
if _UPSTREAM_SRC.exists() and str(_UPSTREAM_SRC) not in sys.path:
    sys.path.insert(0, str(_UPSTREAM_SRC))

VADIterator = None

logger = logging.getLogger("intentlock.vad")


class VADSpeechReport(BaseModel):
    """Structured report detailing speech activity metrics."""
    has_speech: bool
    speech_duration_s: float
    total_duration_s: float
    speech_ratio: float
    segments: List[Dict[str, float]] = []
    onset_s: Optional[float] = None
    offset_s: Optional[float] = None


class SpeechVADService:
    """Silero VAD service providing post-upload validation and streaming turn detection."""

    _instance: Optional["SpeechVADService"] = None

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._model_lock = threading.Lock()
        self.model = None
        self.utils = None
        self._load_model()

    def _load_model(self):
        """Loads and prepares Silero VAD model from PyTorch Hub cache."""
        global torch, VADIterator
        import torch
        try:
            from speech_to_speech.VAD.vad_iterator import VADIterator
        except ImportError:
            VADIterator = None
        try:
            logger.info("Loading Silero VAD model from PyTorch Hub cache...")
            self.model, self.utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                onnx=False,
                trust_repo=True,
            )
            self.model.eval()
            logger.info("Silero VAD model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Silero VAD model: {e}")
            raise

    @classmethod
    def get_instance(cls, threshold: float = 0.5) -> "SpeechVADService":
        if cls._instance is None:
            cls._instance = cls(threshold=threshold)
        return cls._instance

    def validate_speech(
        self,
        audio_16k: np.ndarray,
        threshold: Optional[float] = None,
        min_speech_duration_s: float = 0.25,
        min_speech_ratio: float = 0.04,
    ) -> VADSpeechReport:
        """
        Analyze audio for human speech presence, boundaries, and active duration.

        Args:
            audio_16k: 1D float32 numpy array sampled at 16,000 Hz.
            threshold: Speech probability threshold (default: 0.5).
            min_speech_duration_s: Minimum cumulative speech required (default: 0.25s).
            min_speech_ratio: Minimum ratio of speech to total duration (default: 0.04).

        Returns:
            VADSpeechReport with speech presence flag and boundary metrics.
        """
        if self.model is None or self.utils is None:
            raise RuntimeError("Silero VAD model is not initialized.")

        get_speech_timestamps = self.utils[0]
        thresh = threshold if threshold is not None else self.threshold
        total_duration_s = len(audio_16k) / 16000.0

        tensor_audio = torch.from_numpy(audio_16k)
        # Silero resets mutable model state during a window; serialize preview/final ASR.
        with self._model_lock:
            raw_segments = get_speech_timestamps(
                tensor_audio, self.model, sampling_rate=16000, threshold=thresh,
            )

        segments = []
        total_speech_s = 0.0
        for seg in raw_segments:
            start_s = round(seg["start"] / 16000.0, 3)
            end_s = round(seg["end"] / 16000.0, 3)
            segments.append({"start": start_s, "end": end_s})
            total_speech_s += (end_s - start_s)

        speech_ratio = (total_speech_s / total_duration_s) if total_duration_s > 0 else 0.0
        has_speech = (len(segments) > 0 and total_speech_s >= min_speech_duration_s and speech_ratio >= min_speech_ratio)

        onset_s = segments[0]["start"] if segments else None
        offset_s = segments[-1]["end"] if segments else None

        return VADSpeechReport(
            has_speech=has_speech,
            speech_duration_s=round(total_speech_s, 3),
            total_duration_s=round(total_duration_s, 3),
            speech_ratio=round(speech_ratio, 3),
            segments=segments,
            onset_s=onset_s,
            offset_s=offset_s,
        )

    def create_stream_iterator(
        self,
        threshold: float = 0.5,
        min_silence_duration_ms: int = 400,
        speech_pad_ms: int = 50,
    ) -> Any:
        """
        Create a new streaming VADIterator instance for frame-by-frame turn boundary detection.
        Reuses upstream VADIterator class from speech_hf.

        Args:
            threshold: Speech trigger probability.
            min_silence_duration_ms: Silence duration before marking turn boundary.
            speech_pad_ms: Pre-roll audio padding duration.

        Returns:
            VADIterator instance configured for 16kHz audio stream.
        """
        if VADIterator is None:
            raise RuntimeError("Upstream VADIterator is not available.")
        return VADIterator(
            model=self.model,
            threshold=threshold,
            sampling_rate=16000,
            min_silence_duration_ms=min_silence_duration_ms,
            speech_pad_ms=speech_pad_ms,
        )
