"""
IntentLock — Audio Decoder & WAV Encoder
Decodes multi-format browser audio (WebM/Opus, MP4/M4A, WAV) in-memory
into 16kHz float32 mono arrays for VAD and STT without external ffmpeg binaries.
Also serializes raw synthesized PCM samples to compliant 16-bit PCM WAV containers.
"""

import io
import wave
import numpy as np
from faster_whisper.audio import decode_audio


class AudioDecoder:
    """In-memory audio decoder and PCM WAV serializer."""

    @staticmethod
    def decode_to_16k_mono(
        audio_bytes: bytes,
        max_duration_s: float = 60.0,
        min_duration_s: float = 0.1,
    ) -> np.ndarray:
        """
        Decode arbitrary browser audio bytes into a 16kHz 1D float32 numpy array.
        Enforces duration bounds and finite sample validation.

        Args:
            audio_bytes: Raw binary content of audio container (WebM, WAV, MP4, etc.)
            max_duration_s: Maximum allowable duration in seconds (default: 60.0s)
            min_duration_s: Minimum required duration in seconds (default: 0.1s)

        Returns:
            np.ndarray: 1D float32 array sampled at 16,000 Hz, normalized in [-1.0, 1.0].

        Raises:
            ValueError: If audio is corrupt, empty, non-finite, or violates duration bounds.
        """
        if not audio_bytes or len(audio_bytes) == 0:
            raise ValueError("Audio buffer is empty (0 bytes).")

        try:
            # decode_audio handles WebM/Opus, MP4/M4A, WAV via PyAV in-memory
            audio_np = decode_audio(io.BytesIO(audio_bytes), sampling_rate=16000)
        except Exception as e:
            raise ValueError(f"Failed to decode audio payload: {e}") from e

        if audio_np is None or len(audio_np) == 0:
            raise ValueError("Decoded audio stream contains zero samples.")

        # Ensure 1D float32
        if audio_np.ndim > 1:
            audio_np = audio_np.flatten()
        audio_np = audio_np.astype(np.float32)

        # Validate finiteness
        if not np.isfinite(audio_np).all():
            raise ValueError("Audio contains NaN or Inf sample values.")

        duration_s = len(audio_np) / 16000.0

        if duration_s > max_duration_s:
            raise ValueError(
                f"Audio duration of {duration_s:.2f}s exceeds maximum operational bound of {max_duration_s:.1f}s."
            )

        if duration_s < min_duration_s:
            raise ValueError(
                f"Audio duration of {duration_s:.2f}s is below minimum operational threshold of {min_duration_s:.1f}s."
            )

        return audio_np

    @staticmethod
    def pcm_to_wav_bytes(
        audio_data: np.ndarray,
        sample_rate: int = 24000,
    ) -> bytes:
        """
        Encode raw float32 or int16 PCM audio samples into a standard 16-bit mono WAV byte container.

        Args:
            audio_data: 1D numpy array of audio samples (float32 in [-1.0, 1.0] or int16)
            sample_rate: Audio sampling frequency in Hz (default: 24000 for Kokoro TTS)

        Returns:
            bytes: Valid WAV file binary representation with 44-byte RIFF header.
        """
        if audio_data is None or len(audio_data) == 0:
            return b""

        # Convert float32 [-1.0, 1.0] to int16
        if audio_data.dtype in (np.float32, np.float64):
            clipped = np.clip(audio_data, -1.0, 1.0)
            pcm_int16 = (clipped * 32767.0).astype(np.int16)
        elif audio_data.dtype == np.int16:
            pcm_int16 = audio_data
        else:
            pcm_int16 = audio_data.astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit (2 bytes)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_int16.tobytes())

        return buffer.getvalue()
