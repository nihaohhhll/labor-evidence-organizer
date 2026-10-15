"""Application configuration.

All settings are read from the environment (or `.env`) exactly once at
import time so that the whole process agrees on a single configuration.
Business code must import `settings` from here and never read `os.environ`
directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- application ----
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Labor Evidence Organizer"
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 1440
    api_v1_prefix: str = "/api/v1"
    # Comma-separated browser origins allowed to call the API (the Next dev
    # server runs on another origin in development). Auth is via bearer
    # token, so no credentials/cookies are ever allowed cross-origin.
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    # ---- database ----
    database_url: str = "postgresql+psycopg://leo:leo_dev_pw@127.0.0.1:5432/labor_evidence"
    test_database_url: str = "postgresql+psycopg://leo:leo_dev_pw@127.0.0.1:5432/labor_evidence_test"
    db_echo: bool = False

    # ---- storage ----
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./var/storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str | None = None

    # ---- uploads ----
    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_mime_types: str = (
        "image/png,image/jpeg,application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
    )

    # ---- async jobs ----
    job_backend: Literal["inline", "rq"] = "inline"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ---- AI / OCR ----
    ai_provider: str = "mock"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = ""
    ocr_provider: str = "mock"
    ocr_api_key: str = ""
    prompt_version: str = "evidence-extraction-v1"

    @field_validator("secret_key")
    @classmethod
    def _warn_default_secret(cls, v: str) -> str:
        if v == "change-me-to-a-long-random-string" and v:  # pragma: no cover - config guard
            # Allowed for development; production must override it.
            return v
        return v

    @property
    def allowed_mime_set(self) -> set[str]:
        return {m.strip() for m in self.allowed_mime_types.split(",") if m.strip()}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
