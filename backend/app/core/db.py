from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_connect_args(settings: Settings) -> dict[str, Any]:
    return {
        "check_same_thread": False,
        "timeout": max(settings.sqlite_busy_timeout_ms / 1000.0, 0.1),
    }


def create_db_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    connect_args = _sqlite_connect_args(settings) if settings.database_url and settings.database_url.startswith("sqlite") else {}
    engine = create_engine(
        settings.database_url or "sqlite://",
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )

    if settings.database_url and settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA journal_mode={settings.sqlite_journal_mode}")
            cursor.execute(f"PRAGMA busy_timeout={int(settings.sqlite_busy_timeout_ms)}")
            cursor.execute(f"PRAGMA synchronous={settings.sqlite_synchronous_mode}")
            cursor.close()

    return engine


def init_engine(settings: Settings | None = None) -> Engine:
    global _engine, _SessionLocal
    settings = settings or get_settings()
    if _engine is not None:
        _engine.dispose()
    _engine = create_db_engine(settings)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database_ready(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError as exc:
        logger.warning("database readiness check failed: %s", exc)
        return False


def dispose_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
