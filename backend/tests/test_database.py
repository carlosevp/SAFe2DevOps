from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.core.config import Settings, reset_settings_cache
from app.core.db import check_database_ready, dispose_engine, init_engine
from app.core.migrations import run_migrations
from app.services.storage import StorageService


def test_database_connectivity_and_migrations(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    db_url = f"sqlite:///{data_dir / 'db' / 'safedevops.db'}"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "y" * 32)
    reset_settings_cache()
    dispose_engine()
    settings = Settings()
    StorageService(settings).ensure_directories()
    assert settings.database_url
    run_migrations(settings.database_url)
    engine = init_engine(settings)
    assert check_database_ready(settings) is True
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    names = {row[0] for row in rows}
    assert "access_token_revocations" in names
    assert "alembic_version" in names
