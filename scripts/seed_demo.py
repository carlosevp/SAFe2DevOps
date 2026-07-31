#!/usr/bin/env python3
"""Load deterministic demo assessment data."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory, init_engine  # noqa: E402
from app.core.migrations import run_migrations  # noqa: E402
from app.services.seed import SeedService  # noqa: E402
from app.services.storage import StorageService  # noqa: E402


def main() -> int:
    settings = get_settings()
    StorageService(settings).ensure_directories()
    assert settings.database_url
    run_migrations(settings.database_url)
    init_engine(settings)
    db = get_session_factory()()
    try:
        assessment = SeedService(db).seed_demo(publish=True)
        db.commit()
        print(f"Seeded assessment id={assessment.id} status={assessment.status} team={assessment.team_name}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
