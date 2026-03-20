"""
Cấu hình hệ thống — đọc từ .env qua Pydantic BaseSettings.
Tất cả secrets và env-specific config phải khai báo ở đây, KHÔNG hardcode trong code.
"""

from typing import Literal
from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM Provider ────────────────────────────────────────
    # "gemini" = Google Vertex AI (cloud), "ollama" = local Ollama
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"

    # ── Google Cloud Vertex AI (khi LLM_PROVIDER=gemini) ────
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = True
    GEMINI_MODEL: str = "gemini-2.0-flash-001"
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # ── Ollama (khi LLM_PROVIDER=ollama) ────────────────────
    OLLAMA_MODEL: str = "qwen2.5:14b"
    OLLAMA_HOST: str = "http://localhost:11434"
    # Model nhỏ hơn cho agents đơn giản (Agent 0, 1, 1.5) — tiết kiệm RAM
    OLLAMA_SMALL_MODEL: str = ""  # Rỗng = dùng OLLAMA_MODEL cho tất cả

    # ── Paths ───────────────────────────────────────────────
    BASE_DIR: Path = Path(__file__).parent
    GENERATED_CHECKS_DIR: Path = Path("generated_checks")
    REPORTS_DIR: Path = Path("reports")
    DATA_DIR: Path = Path("data")

    # ── Pipeline ────────────────────────────────────────────
    MAX_RETRY_AGENT4: int = 3
    MAX_RETRY_AGENT5: int = 3
    SANDBOX_TIMEOUT: int = 30  # seconds — subprocess timeout (Agent 3)
    LLM_TIMEOUT: int = 120  # seconds — timeout cho mỗi LLM agent call (0 = no timeout)
    MAX_CONCURRENT_RULES: int = 3  # Số rules xử lý song song (1 = tuần tự)
    STDOUT_TRUNCATION: int = 5000  # chars — agent stdout truncation
    STDERR_TRUNCATION: int = 3000  # chars — agent stderr truncation
    CACHE_SUMMARY_LIMIT: int = 2000  # chars — exploration cache summary truncation

    @model_validator(mode="after")
    def validate_provider_config(self):
        if self.LLM_PROVIDER == "gemini":
            if not self.GOOGLE_CLOUD_PROJECT or not self.GOOGLE_CLOUD_PROJECT.strip():
                raise ValueError(
                    "LLM_PROVIDER=gemini nhưng GOOGLE_CLOUD_PROJECT trống. "
                    "Set GOOGLE_CLOUD_PROJECT trong .env hoặc đổi LLM_PROVIDER=ollama."
                )
        return self

    @field_validator("GENERATED_CHECKS_DIR", "REPORTS_DIR", mode="before")
    @classmethod
    def ensure_dirs_exist(cls, v) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
