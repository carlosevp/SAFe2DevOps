from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import reset_settings_cache

logger = logging.getLogger(__name__)


def run_migrations(database_url: str) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    os.environ["DATABASE_URL"] = database_url
    reset_settings_cache()

    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("path_separator", "os")
    logger.info("running database migrations")
    command.upgrade(cfg, "head")
