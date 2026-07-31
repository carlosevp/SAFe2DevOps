from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_settings_cache
from app.core.db import dispose_engine
from app.core.security import hash_password
from app.main import create_app


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture()
def admin_password() -> str:
    return "test-admin-password"


@pytest.fixture()
def app_env(tmp_data_dir: Path, admin_password: str, tmp_path: Path) -> Generator[dict[str, str], None, None]:
    dist = tmp_path / "frontend-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><html><body>SPA</body></html>", encoding="utf-8")
    (dist / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    env = {
        "APP_ENV": "test",
        "DATA_DIR": str(tmp_data_dir),
        "DATABASE_URL": f"sqlite:///{tmp_data_dir / 'db' / 'safedevops.db'}",
        "APP_SECRET_KEY": "unit-test-app-secret-key-32-bytes!!",
        "DATA_ENCRYPTION_KEY": "unit-test-data-encryption-key-32b!",
        "ADMIN_PASSWORD_HASH": hash_password(admin_password),
        "FRONTEND_DIST": str(dist),
        "CORS_ORIGINS": "http://testserver",
        "LOG_LEVEL": "WARNING",
        "ASSESSMENT_CONFIG_PATH": str(repo_root / "config" / "assessment" / "assessment_model.yaml"),
        "INTEGRATION_PROVIDER": "mock",
        "INTERVIEW_PROVIDER": "mock",
    }
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    reset_settings_cache()
    dispose_engine()
    yield env
    dispose_engine()
    reset_settings_cache()
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def client(app_env: dict[str, str]) -> Generator[TestClient, None, None]:
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
