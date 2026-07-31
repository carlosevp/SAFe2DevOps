from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.core.config import Settings, reset_settings_cache
from app.core.errors import AppError
from app.core.migrations import run_migrations
from app.services.backup import BackupService
from app.services.storage import StorageService


def _ready(tmp_path: Path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        database_url=None,
        app_secret_key="x" * 32,
        data_encryption_key="y" * 32,
    )
    StorageService(settings).ensure_directories()
    assert settings.database_url
    run_migrations(settings.database_url)
    return settings


def test_backup_create_list_verify(tmp_path: Path) -> None:
    settings = _ready(tmp_path)
    service = BackupService(settings)
    info = service.create_backup(label="unit")
    assert info.integrity_ok is True
    assert info.name.startswith("safedevops-")
    listed = service.list_backups()
    assert any(item.name == info.name for item in listed)
    assert service.verify_integrity(info.name) is True


def test_backup_vacuum_into(tmp_path: Path) -> None:
    settings = _ready(tmp_path)
    service = BackupService(settings)
    info = service.create_backup(label="vac", method="vacuum_into")
    assert service.verify_integrity(info.name) is True


def test_restore_and_storage_usage(tmp_path: Path) -> None:
    settings = _ready(tmp_path)
    service = BackupService(settings)
    info = service.create_backup(label="restore-me")

    # Mutate live DB then restore.
    db = settings.sqlite_path
    assert db is not None
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS ops_probe (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO ops_probe(id) VALUES (1)")
    conn.commit()
    conn.close()

    restored = service.restore(info.name, force=True)
    assert restored.integrity_ok is True
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "ops_probe" not in tables

    usage = service.storage_usage()
    assert usage["total_bytes"] >= 0
    assert "bytes_by_label" in usage


def test_clean_temp_never_removes_exports_or_backups(tmp_path: Path) -> None:
    settings = _ready(tmp_path)
    service = BackupService(settings)
    paths = StorageService(settings).paths()
    export = paths.exports / "keep-me.txt"
    export.write_text("report", encoding="utf-8")
    backup = paths.backups / "safedevops-keep.db"
    backup.write_bytes(b"not-a-real-db-but-must-remain")
    temp = paths.working / "stale.tmp"
    temp.write_text("tmp", encoding="utf-8")
    # Age the temp file
    import os
    import time

    past = time.time() - 10_000
    os.utime(temp, (past, past))

    result = service.clean_expired_temp_files(max_age_seconds=60)
    assert result["removed"] >= 1
    assert export.exists()
    assert backup.exists()
    assert not temp.exists()


def test_restore_refuses_when_wal_present(tmp_path: Path) -> None:
    settings = _ready(tmp_path)
    service = BackupService(settings)
    info = service.create_backup(label="wal-guard")
    db = settings.sqlite_path
    assert db is not None
    (Path(str(db) + "-wal")).write_bytes(b"x")
    with pytest.raises(AppError) as exc:
        service.restore(info.name, force=False)
    assert exc.value.code == "database_in_use"
    reset_settings_cache()
