from __future__ import annotations

from pathlib import Path

import pytest

from app.core.bootstrap import bootstrap_runtime, validate_configuration
from app.core.config import Settings


def _settings(tmp_path: Path, **kwargs) -> Settings:
    defaults = dict(
        app_env="test",
        data_dir=tmp_path / "data",
        database_url=None,
        app_secret_key="x" * 32,
        data_encryption_key="y" * 32,
        assessment_config_path=Path(__file__).resolve().parents[2]
        / "config"
        / "assessment"
        / "assessment_model.yaml",
    )
    defaults.update(kwargs)
    return Settings(**defaults)


def test_default_journal_is_delete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SQLITE_JOURNAL_MODE", raising=False)
    settings = _settings(tmp_path)
    assert settings.sqlite_journal_mode == "DELETE"
    assert settings.sqlite_synchronous_mode == "FULL"


def test_validate_rejects_unknown_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path, sqlite_journal_mode="NOT_REAL")
    with pytest.raises(RuntimeError, match="Unsupported SQLITE_JOURNAL_MODE"):
        validate_configuration(settings)


def test_bootstrap_creates_layout_and_migrates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "y" * 32)
    monkeypatch.setenv(
        "ASSESSMENT_CONFIG_PATH",
        str(
            Path(__file__).resolve().parents[2]
            / "config"
            / "assessment"
            / "assessment_model.yaml"
        ),
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.core.config import reset_settings_cache

    reset_settings_cache()
    settings = bootstrap_runtime(run_db_migrations=True)
    data = settings.data_dir
    for name in ("db", "uploads", "exports", "evidence", "backups", "working"):
        assert (data / name).is_dir()
    assert (data / "db" / "safedevops.db").exists()


def test_bootstrap_refuses_db_outside_data_db(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere" / "app.db"
    outside.parent.mkdir(parents=True)
    settings = _settings(tmp_path, database_url=f"sqlite:///{outside}")
    with pytest.raises(RuntimeError, match="data/db"):
        validate_configuration(settings)
