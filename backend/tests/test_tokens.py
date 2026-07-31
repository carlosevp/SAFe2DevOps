from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, reset_settings_cache
from app.core.db import dispose_engine, get_session_factory, init_engine
from app.core.errors import AppError
from app.core.migrations import run_migrations
from app.core.security import verify_assessment_access_token
from app.services.storage import StorageService
from app.services.tokens import AssessmentAccessTokenService


def test_assessment_access_token_issue_verify_revoke(tmp_path: Path, monkeypatch) -> None:
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
    init_engine(settings)

    service = AssessmentAccessTokenService(settings)
    issued = service.issue(assessment_id="assessment-1", role="remote")
    payload = verify_assessment_access_token(settings, issued["token"])
    assert payload["jti"] == issued["jti"]

    db = get_session_factory()()
    try:
        verified = service.verify(db, issued["token"])
        assert verified["assessment_id"] == "assessment-1"
        service.revoke(db, jti=issued["jti"], assessment_id="assessment-1", reason="test")
        db.commit()
        with pytest.raises(AppError) as exc:
            service.verify(db, issued["token"])
        assert exc.value.code == "token_revoked"
    finally:
        db.close()
