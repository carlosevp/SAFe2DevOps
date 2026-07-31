from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.services.storage import StorageService


def test_storage_creates_writable_directories(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        app_secret_key="x" * 32,
        data_encryption_key="y" * 32,
    )
    service = StorageService(settings)
    paths = service.ensure_directories()

    assert paths.db_dir.is_dir()
    assert paths.uploads.is_dir()
    assert paths.exports.is_dir()
    assert paths.evidence.is_dir()
    assert paths.backups.is_dir()
    assert paths.working.is_dir()
    assert service.validate_ready() is True

    labels = paths.as_public_labels()
    assert "data/db" in labels.values()
    assert not any(str(tmp_path) in value for value in labels.values())
