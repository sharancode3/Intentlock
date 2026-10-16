"""
IntentLock — Backend Core Configuration
Defines application settings, upload bounds, allowed media types,
configured CORS origins, and upstream connector placeholders.
"""

import json
import os
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "IntentLock Backend"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Workspace Paths
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    DATA_PATH: str = os.path.join(BASE_DIR, "backend", "data", "all_employees.json")

    # Explicit Frontend Origins Allowlist (No Wildcards)
    FRONTEND_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Bounded Upload Limits (Bytes)
    MAX_AUDIO_BYTES: int = 8 * 1024 * 1024  # 8 MiB operational audio cap
    MAX_REQUEST_BYTES: int = 10 * 1024 * 1024  # 10 MiB total multipart request cap

    # Allowed Audio MIME Types
    ALLOWED_AUDIO_TYPES: List[str] = [
        "audio/webm",
        "audio/mp4",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/mpeg",
        "audio/aac",
        "audio/m4a",
        "audio/x-m4a",
    ]

    # Local Ollama Settings (Knowledge retrieval)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "3.0"))

    # Service Security
    INTENTLOCK_SERVICE_KEY: str = os.getenv("INTENTLOCK_SERVICE_KEY", "intentlock_local_dev_key")

    # Speech Pipeline Configuration
    ENABLE_SPEECH_PIPELINE: bool = True
    SPEECH_STT_MODEL: str = os.getenv("SPEECH_STT_MODEL", "tiny.en")
    SPEECH_STT_DEVICE: str = os.getenv("SPEECH_STT_DEVICE", "cpu")
    SPEECH_STT_COMPUTE_TYPE: str = os.getenv("SPEECH_STT_COMPUTE_TYPE", "int8")
    SPEECH_TTS_VOICE: str = os.getenv("SPEECH_TTS_VOICE", "af_heart")
    SPEECH_TTS_LANG: str = os.getenv("SPEECH_TTS_LANG", "a")
    SPEECH_TTS_SPEED: float = float(os.getenv("SPEECH_TTS_SPEED", "1.0"))
    SPEECH_VAD_THRESHOLD: float = float(os.getenv("SPEECH_VAD_THRESHOLD", "0.5"))

    # DetectifAI Biometric Settings (Stage 2)
    DETECTIF_BASE_URL: str = os.getenv("DETECTIF_BASE_URL", "https://platform.detectif.ai/v1")
    DETECTIF_API_KEY: Optional[str] = os.getenv("DETECTIF_API_KEY", None)
    DETECTIF_ACCOUNT_ALIAS: str = os.getenv("DETECTIF_ACCOUNT_ALIAS", "primary_account")
    DETECTIF_TIMEOUT_SECONDS: float = float(os.getenv("DETECTIF_TIMEOUT_SECONDS", "15.0"))
    DETECTIF_MAX_RETRIES: int = int(os.getenv("DETECTIF_MAX_RETRIES", "2"))
    SPEECH_SERVICE_URL: Optional[str] = None

    # LLM & Knowledge Generation Settings (Stage 3)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    OPENAI_TIMEOUT_SECONDS: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20.0"))
    OPENAI_MAX_OUTPUT_TOKENS: int = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1024"))
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "1"))

    # Session & Identity Configuration
    SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "90"))
    OPERATOR_SECRET_KEY: Optional[str] = os.getenv("OPERATOR_SECRET_KEY", None)
    MAPPING_DB_PATH: str = os.getenv(
        "MAPPING_DB_PATH",
        os.path.join(BASE_DIR, "backend", "data", "identity_mappings.sqlite3"),
    )

    @field_validator("FRONTEND_ORIGINS", "ALLOWED_AUDIO_TYPES", mode="before")
    @classmethod
    def parse_string_list(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in v_trimmed.split(",") if item.strip()]
        return v

    def get_safe_diagnostics(self) -> dict:
        """Returns non-sensitive configuration summary with redacted secrets."""
        return {
            "environment": self.ENVIRONMENT,
            "detectif_configured": bool(self.DETECTIF_API_KEY),
            "detectif_base_url": self.DETECTIF_BASE_URL,
            "detectif_account_alias": self.DETECTIF_ACCOUNT_ALIAS,
            "llm_provider": self.LLM_PROVIDER,
            "openai_configured": bool(self.OPENAI_API_KEY),
            "openai_model": self.OPENAI_MODEL,
            "session_ttl_seconds": self.SESSION_TTL_SECONDS,
            "speech_pipeline_enabled": self.ENABLE_SPEECH_PIPELINE,
            "speech_stt_model": self.SPEECH_STT_MODEL,
            "speech_tts_voice": self.SPEECH_TTS_VOICE,
            "operator_key_configured": bool(self.OPERATOR_SECRET_KEY),
        }

    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
            ".env",
        ),
        extra="ignore",
    )


settings = Settings()

