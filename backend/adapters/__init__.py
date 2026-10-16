"""
IntentLock — Speech & Audio Adapters
Real Open-Source Hugging Face Speech-to-Speech Integration
Provides:
- AudioDecoder: Decode WebM/Opus, MP4/M4A, WAV to 16kHz float32 mono
- SpeechVADService: Silero VAD post-upload segmentation & streaming turn boundary iterator
- FasterWhisperSTTAdapter: Faster-Whisper CPU int8 transcription
- KokoroTTSAdapter: Kokoro-82M 24kHz neural speech synthesis
"""

from backend.adapters.audio_decoder import AudioDecoder
from backend.adapters.speech_vad import SpeechVADService, VADSpeechReport
from backend.adapters.speech_stt import FasterWhisperSTTAdapter
from backend.adapters.speech_tts import KokoroTTSAdapter

__all__ = [
    "AudioDecoder",
    "SpeechVADService",
    "VADSpeechReport",
    "FasterWhisperSTTAdapter",
    "KokoroTTSAdapter",
]
