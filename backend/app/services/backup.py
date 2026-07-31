from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
TEMP_GLOBS = ("*.tmp", "*.temp", ".tmp-*", "*.partial", ".write_probe")


@dataclass(frozen=True, slots=True)
class BackupInfo:
    name: str
    relpath: str
    size_bytes: int
    created_at: str
    integrity_ok: bool | None = None


class BackupService:
    """SQLite backups via the backup API / VACUUM INTO — never copy a live DB file."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.storage = StorageService(self.settings)

    def create_backup(self, *, label: str | None = None, method: str = "backup_api") -> BackupInfo:
        paths = self.storage.ensure_directories()
        db_path = self.settings.sqlite_path
        if (
            db_path is None
            or not self.settings.database_url
            or not self.settings.database_url.startswith("sqlite")
        ):
            raise AppError(
                code="sqlite_required", message="Backups require a SQLite database", status_code=400
            )
        if not db_path.exists():
            raise AppError(
                code="database_missing",
                message="SQLite database file does not exist",
                status_code=404,
            )

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_label = SAFE_NAME_RE.sub("_", (label or "manual").strip())[:40] or "manual"
        filename = f"safedevops-{stamp}-{safe_label}.db"
        target = paths.backups / filename
        if target.exists():
            raise AppError(
                code="backup_exists", message="Backup filename already exists", status_code=409
            )

        if method == "vacuum_into":
            self._vacuum_into(db_path, target)
        else:
            self._backup_api(db_path, target)

        integrity = self.verify_integrity(target)
        if not integrity:
            target.unlink(missing_ok=True)
            raise AppError(
                code="backup_corrupt",
                message="Backup failed integrity check and was discarded",
                status_code=500,
            )

        return BackupInfo(
            name=filename,
            relpath=f"data/backups/{filename}",
            size_bytes=target.stat().st_size,
            created_at=datetime.now(UTC).isoformat(),
            integrity_ok=True,
        )

    def list_backups(self) -> list[BackupInfo]:
        paths = self.storage.ensure_directories()
        items: list[BackupInfo] = []
        for path in sorted(paths.backups.glob("safedevops-*.db"), reverse=True):
            items.append(
                BackupInfo(
                    name=path.name,
                    relpath=f"data/backups/{path.name}",
                    size_bytes=path.stat().st_size,
                    created_at=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                )
            )
        return items

    def verify_integrity(self, backup: Path | str) -> bool:
        path = Path(backup) if not isinstance(backup, Path) else backup
        if not path.is_absolute():
            path = self.storage.paths().backups / path.name
        if not path.is_file():
            raise AppError(
                code="backup_not_found", message="Backup file not found", status_code=404
            )
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row and row[0] == "ok")
        finally:
            conn.close()

    def restore(self, backup_name: str, *, force: bool = False) -> BackupInfo:
        """Restore while the application is stopped. Refuses if the live DB appears locked."""
        paths = self.storage.ensure_directories()
        source = paths.backups / Path(backup_name).name
        if not source.is_file():
            raise AppError(
                code="backup_not_found", message="Backup file not found", status_code=404
            )
        if not self.verify_integrity(source):
            raise AppError(
                code="backup_corrupt", message="Backup failed integrity check", status_code=400
            )

        db_path = self.settings.sqlite_path
        if db_path is None:
            raise AppError(
                code="sqlite_required",
                message="SQLite database path is not configured",
                status_code=400,
            )

        # Refuse restore if a writer lock suggests the app is still running.
        wal = Path(str(db_path) + "-wal")
        shm = Path(str(db_path) + "-shm")
        journal = Path(str(db_path) + "-journal")
        if (wal.exists() or shm.exists()) and not force:
            raise AppError(
                code="database_in_use",
                message="Live database appears in use (WAL/SHM present). Stop the application before restore.",
                status_code=409,
            )
        if journal.exists() and journal.stat().st_size > 0 and not force:
            raise AppError(
                code="database_in_use",
                message="Live database journal present. Stop the application before restore.",
                status_code=409,
            )

        db_path.parent.mkdir(parents=True, exist_ok=True)
        staging = db_path.with_suffix(".restore-tmp")
        shutil.copy2(source, staging)
        os.replace(staging, db_path)
        # Remove journal/WAL sidecars from prior runtime so the restored file starts clean.
        for sidecar in (wal, shm, journal):
            sidecar.unlink(missing_ok=True)

        return BackupInfo(
            name=source.name,
            relpath=f"data/backups/{source.name}",
            size_bytes=source.stat().st_size,
            created_at=datetime.fromtimestamp(source.stat().st_mtime, UTC).isoformat(),
            integrity_ok=True,
        )

    def storage_usage(self) -> dict[str, object]:
        paths = self.storage.ensure_directories()
        usage = {
            "db": self._dir_size(paths.db_dir),
            "uploads": self._dir_size(paths.uploads),
            "exports": self._dir_size(paths.exports),
            "evidence": self._dir_size(paths.evidence),
            "backups": self._dir_size(paths.backups),
            "working": self._dir_size(paths.working),
        }
        return {
            "labels": paths.as_public_labels(),
            "bytes_by_label": usage,
            "total_bytes": sum(usage.values()),
        }

    def clean_expired_temp_files(self, *, max_age_seconds: int = 3600) -> dict[str, int]:
        """Remove expired temporary files only. Never touch active assessment/report data."""
        paths = self.storage.ensure_directories()
        removed = 0
        skipped = 0
        now = datetime.now(UTC).timestamp()
        # Only scan working/ and explicit temp names under uploads/voice tmp markers.
        scan_roots = [paths.working]
        voice_tmp = paths.uploads / "voice"
        if voice_tmp.is_dir():
            scan_roots.append(voice_tmp)

        protected_roots = {
            paths.db_dir.resolve(),
            paths.exports.resolve(),
            paths.evidence.resolve(),
            paths.backups.resolve(),
        }
        for root in scan_roots:
            if not root.exists():
                continue
            if root.resolve() in protected_roots:
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                name = path.name
                if not any(
                    path.match(glob) or Path(name).match(glob) for glob in TEMP_GLOBS
                ) and not name.startswith(".tmp"):
                    # Also clean zero-byte probe leftovers.
                    if name != ".write_probe":
                        skipped += 1
                        continue
                age = now - path.stat().st_mtime
                if age < max_age_seconds and name != ".write_probe":
                    skipped += 1
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    skipped += 1
        return {"removed": removed, "skipped": skipped}

    @staticmethod
    def _backup_api(source: Path, target: Path) -> None:
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()

    @staticmethod
    def _vacuum_into(source: Path, target: Path) -> None:
        # VACUUM INTO requires a literal path; keep it under our controlled backup directory.
        safe_target = target.resolve().as_posix().replace("'", "")
        conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            conn.execute(f"VACUUM INTO '{safe_target}'")
        finally:
            conn.close()

    @staticmethod
    def _dir_size(directory: Path) -> int:
        total = 0
        if not directory.exists():
            return 0
        for path in directory.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total
