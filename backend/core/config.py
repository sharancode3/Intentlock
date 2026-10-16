"""
IntentLock — Backend Core Configuration
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "IntentLock Backend"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Workspace Paths
    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    DATA_PATH: str = os.path.join(BASE_DIR, "backend", "data", "all_employees.json")

    # Local Ollama Settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "3.0"))

    # Service Security
    INTENTLOCK_SERVICE_KEY: str = os.getenv("INTENTLOCK_SERVICE_KEY", "intentlock_local_dev_key")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
