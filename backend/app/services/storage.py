from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StoragePaths:
    data_dir: Path
    db_dir: Path
    uploads: Path
    exports: Path
    evidence: Path
    backups: Path
    working: Path

    def as_public_labels(self) -> dict[str, str]:
        """Return logical labels only — never absolute filesystem paths."""
        return {
            "data": "data",
            "db": "data/db",
            "uploads": "data/uploads",
            "exports": "data/exports",
            "evidence": "data/evidence",
            "backups": "data/backups",
            "working": "data/working",
        }


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def paths(self) -> StoragePaths:
        data_dir = self.settings.data_dir
        db_dir = data_dir / "db"
        return StoragePaths(
            data_dir=data_dir,
            db_dir=db_dir,
            uploads=self.settings.upload_dir or data_dir / "uploads",
            exports=self.settings.export_dir or data_dir / "exports",
            evidence=self.settings.evidence_dir or data_dir / "evidence",
            backups=self.settings.backup_dir or data_dir / "backups",
            working=self.settings.working_dir or data_dir / "working",
        )

    def ensure_directories(self) -> StoragePaths:
        paths = self.paths()
        for directory in (
            paths.data_dir,
            paths.db_dir,
            paths.uploads,
            paths.exports,
            paths.evidence,
            paths.backups,
            paths.working,
        ):
            directory.mkdir(parents=True, exist_ok=True)
            self._assert_writable(directory)
        logger.info(
            "storage directories ready labels=%s", sorted(paths.as_public_labels().values())
        )
        return paths

    def validate_ready(self) -> bool:
        try:
            paths = self.ensure_directories()
        except OSError:
            return False
        return all(
            path.is_dir() and os.access(path, os.W_OK)
            for path in (
                paths.data_dir,
                paths.db_dir,
                paths.uploads,
                paths.exports,
                paths.evidence,
                paths.backups,
                paths.working,
            )
        )

    @staticmethod
    def _assert_writable(directory: Path) -> None:
        probe = directory / ".write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise AppError(
                code="storage_not_writable",
                message="Runtime storage directory is not writable",
                status_code=500,
                details={"label": directory.name},
            ) from exc
