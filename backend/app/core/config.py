from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    port: int = 8000
    data_dir: Path = Field(default_factory=lambda: Path("./data"))

    database_url: str | None = None
    upload_dir: Path | None = None
    export_dir: Path | None = None
    evidence_dir: Path | None = None
    backup_dir: Path | None = None
    working_dir: Path | None = None

    app_secret_key: str = ""
    data_encryption_key: str = ""
    admin_password_hash: str = ""

    openai_api_key: str = ""
    openai_assessment_model: str = "gpt-5.6-terra"
    openai_transcription_model: str = "gpt-realtime-whisper"
    openai_reasoning_effort: str = "medium"

    # Default DELETE (rollback journal) is portable across unknown/network-backed volumes.
    # Use WAL only when the storage platform is explicitly validated for it.
    sqlite_journal_mode: str = "DELETE"
    sqlite_busy_timeout_ms: int = 5000
    sqlite_synchronous_mode: str = "FULL"

    session_cookie_name: str = "sd_admin_session"
    session_ttl_seconds: int = 60 * 60 * 12
    assessment_token_ttl_seconds: int = 60 * 60 * 24 * 7
    remote_invite_ttl_seconds: int = 60 * 60 * 24 * 7
    public_base_url: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8443"
    frontend_dist: Path | None = None
    assessment_config_path: Path | None = None
    log_level: str = "INFO"
    seed_demo_data: bool = False
    integration_provider: Literal["mock", "live"] = "mock"
    interview_provider: Literal["mock", "live"] = "mock"

    @field_validator(
        "data_dir",
        "upload_dir",
        "export_dir",
        "evidence_dir",
        "backup_dir",
        "working_dir",
        "frontend_dist",
        "assessment_config_path",
        mode="before",
    )
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return Path(value)
        return value

    @model_validator(mode="after")
    def _derive_paths(self) -> Settings:
        data_dir = self.data_dir
        if not data_dir.is_absolute():
            data_dir = (_repo_root() / data_dir).resolve()
            self.data_dir = data_dir

        self.upload_dir = (self.upload_dir or data_dir / "uploads").resolve()
        self.export_dir = (self.export_dir or data_dir / "exports").resolve()
        self.evidence_dir = (self.evidence_dir or data_dir / "evidence").resolve()
        self.backup_dir = (self.backup_dir or data_dir / "backups").resolve()
        self.working_dir = (self.working_dir or data_dir / "working").resolve()

        if not self.database_url:
            db_path = (data_dir / "db" / "safedevops.db").resolve()
            self.database_url = f"sqlite:///{db_path}"

        if self.frontend_dist is None:
            candidate = _repo_root() / "frontend" / "dist"
            packaged = Path("/app/frontend/dist")
            self.frontend_dist = packaged if packaged.exists() else candidate
        else:
            self.frontend_dist = self.frontend_dist.resolve()

        if not self.app_secret_key:
            if self.app_env in {"development", "test"}:
                self.app_secret_key = secrets.token_urlsafe(48)
            else:
                raise ValueError("APP_SECRET_KEY is required outside development/test")
        if not self.data_encryption_key:
            if self.app_env in {"development", "test"}:
                self.data_encryption_key = secrets.token_urlsafe(48)
            else:
                raise ValueError("DATA_ENCRYPTION_KEY is required outside development/test")

        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    @property
    def sqlite_path(self) -> Path | None:
        if not self.database_url or not self.database_url.startswith("sqlite"):
            return None
        raw = self.database_url.removeprefix("sqlite:///").removeprefix("sqlite://")
        return Path(raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
