from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def test_settings_derive_data_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ASSESSMENT_CONFIG_PATH", raising=False)
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        database_url=None,
        app_secret_key="x" * 32,
        data_encryption_key="y" * 32,
    )
    assert settings.data_dir == (tmp_path / "data").resolve()
    assert settings.upload_dir == (tmp_path / "data" / "uploads").resolve()
    assert settings.export_dir == (tmp_path / "data" / "exports").resolve()
    assert settings.evidence_dir == (tmp_path / "data" / "evidence").resolve()
    assert settings.backup_dir == (tmp_path / "data" / "backups").resolve()
    assert settings.working_dir == (tmp_path / "data" / "working").resolve()
    assert settings.database_url is not None
    assert settings.database_url.endswith("/data/db/safedevops.db")
    assert settings.openai_assessment_model == "gpt-5.6-terra"
    assert settings.openai_transcription_model  # may come from env/.env
    assert settings.sqlite_busy_timeout_ms == 5000
    assert settings.sqlite_journal_mode == "DELETE"
    assert settings.sqlite_synchronous_mode == "FULL"


def test_cors_origin_list_parsing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        database_url=None,
        cors_origins="http://a.example, http://b.example",
        app_secret_key="x" * 32,
        data_encryption_key="y" * 32,
    )
    assert settings.cors_origin_list == ["http://a.example", "http://b.example"]
