from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.assessment_config import load_assessment_model_config, reset_assessment_model_cache
from app.core.config import Settings, get_settings, reset_settings_cache
from app.core.logging import configure_logging
from app.core.migrations import run_migrations
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

ALLOWED_JOURNAL_MODES = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}


def validate_configuration(settings: Settings) -> None:
    if settings.app_env in {"staging", "production"}:
        if not settings.app_secret_key:
            raise RuntimeError("APP_SECRET_KEY is required")
        if not settings.data_encryption_key:
            raise RuntimeError("DATA_ENCRYPTION_KEY is required")
    journal = (settings.sqlite_journal_mode or "").upper()
    if journal not in ALLOWED_JOURNAL_MODES:
        raise RuntimeError(f"Unsupported SQLITE_JOURNAL_MODE={settings.sqlite_journal_mode}")
    if settings.sqlite_busy_timeout_ms < 100:
        raise RuntimeError("SQLITE_BUSY_TIMEOUT_MS must be >= 100")
    if settings.allow_mock_host_auth and settings.app_env in {"staging", "production"}:
        raise RuntimeError("ALLOW_MOCK_HOST_AUTH cannot be enabled outside development/test")
    if settings.allow_mock_host_auth:
        logger.warning("ALLOW_MOCK_HOST_AUTH enabled — unauthenticated mock-host admin is active")
    if settings.database_url and settings.database_url.startswith("sqlite"):
        db_path = settings.sqlite_path
        if db_path is None:
            raise RuntimeError("Unable to resolve SQLite database path")
        # Keep database and journal sidecars in the same directory under DATA_DIR/db.
        expected_db_dir = (settings.data_dir / "db").resolve()
        if db_path.parent.resolve() != expected_db_dir:
            raise RuntimeError(
                f"SQLite database must live under data/db (expected {expected_db_dir}, got {db_path.parent})"
            )


def log_storage_diagnostics(settings: Settings, storage: StorageService) -> None:
    paths = storage.paths()
    db_path = settings.sqlite_path
    logger.info(
        "storage diagnostics labels=%s journal_mode=%s busy_timeout_ms=%s synchronous=%s "
        "db_present=%s frontend_dist_present=%s",
        sorted(paths.as_public_labels().values()),
        settings.sqlite_journal_mode,
        settings.sqlite_busy_timeout_ms,
        settings.sqlite_synchronous_mode,
        bool(db_path and db_path.exists()),
        Path(settings.frontend_dist).exists() if settings.frontend_dist else False,
    )


def bootstrap_runtime(*, run_db_migrations: bool = True) -> Settings:
    """Validate config, prepare /data layout, validate YAML, optionally migrate."""
    reset_settings_cache()
    settings = get_settings()
    configure_logging(settings.log_level)
    validate_configuration(settings)

    storage = StorageService(settings)
    storage.ensure_directories()
    if not storage.validate_ready():
        raise RuntimeError("Persistence directories are not writable")

    reset_assessment_model_cache()
    load_assessment_model_config(settings.assessment_config_path)

    if run_db_migrations:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required for migrations")
        try:
            run_migrations(settings.database_url)
        except Exception:
            logger.exception("database migrations failed; refusing startup")
            raise

    log_storage_diagnostics(settings, storage)
    return settings


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    migrate = "--skip-migrations" not in argv
    try:
        bootstrap_runtime(run_db_migrations=migrate)
    except Exception as exc:  # noqa: BLE001
        print(f"bootstrap failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
