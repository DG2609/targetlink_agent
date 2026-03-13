"""
Cấu hình hệ thống — đọc từ .env qua Pydantic BaseSettings.
Tất cả secrets và env-specific config phải khai báo ở đây, KHÔNG hardcode trong code.
"""

from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Google Cloud Vertex AI ──────────────────────────────
    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GOOGLE_GENAI_USE_VERTEXAI: bool = True
    GEMINI_MODEL: str = "gemini-2.0-flash-001"

    # Service Account (để trống nếu dùng ADC)
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # ── Paths ───────────────────────────────────────────────
    BASE_DIR: Path = Path(__file__).parent
    GENERATED_CHECKS_DIR: Path = Path("generated_checks")
    REPORTS_DIR: Path = Path("reports")
    DATA_DIR: Path = Path("data")

    # ── Pipeline ────────────────────────────────────────────
    MAX_RETRY_AGENT4: int = 3
    MAX_RETRY_AGENT5: int = 3
    SANDBOX_TIMEOUT: int = 30  # seconds
    MAX_CONCURRENT_RULES: int = 3  # Số rules xử lý song song (1 = tuần tự)

    @field_validator("GOOGLE_CLOUD_PROJECT")
    @classmethod
    def project_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("GOOGLE_CLOUD_PROJECT không được để trống trong .env")
        return v.strip()

    @field_validator("GENERATED_CHECKS_DIR", "REPORTS_DIR", mode="before")
    @classmethod
    def ensure_dirs_exist(cls, v) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
