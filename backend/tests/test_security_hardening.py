from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import reset_settings_cache
from app.core.db import dispose_engine, get_session_factory
from app.core.rate_limit import rate_limiter
from app.main import create_app
from app.services.seed import SeedService


def test_participant_coverage_requires_auth_without_mock_bypass(
    app_env: dict[str, str], admin_password: str, tmp_data_dir
) -> None:
    os.environ["ALLOW_MOCK_HOST_AUTH"] = "false"
    reset_settings_cache()
    dispose_engine()
    application = create_app()
    with TestClient(application) as client:
        db = get_session_factory()()
        try:
            seed = SeedService(db).seed_demo(publish=False)
            db.commit()
            assessment_id = seed.id
        finally:
            db.close()

        anonymous = client.get(f"/api/assessments/{assessment_id}/coverage/participant")
        assert anonymous.status_code == 401

        login = client.post("/api/auth/admin/login", json={"password": admin_password})
        assert login.status_code == 200
        ok = client.get(f"/api/assessments/{assessment_id}/coverage/participant")
        assert ok.status_code == 200
        assert all("ai_candidate_score" not in row for row in ok.json())

    os.environ["ALLOW_MOCK_HOST_AUTH"] = "true"
    reset_settings_cache()
    dispose_engine()


def test_admin_login_rate_limited(client: TestClient) -> None:
    rate_limiter._events.clear()  # noqa: SLF001
    try:
        for _ in range(5):
            response = client.post("/api/auth/admin/login", json={"password": "wrong-password"})
            assert response.status_code in {401, 403}
        limited = client.post("/api/auth/admin/login", json={"password": "wrong-password"})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
    finally:
        rate_limiter._events.clear()  # noqa: SLF001


def test_csrf_rejects_cross_site_fetch_header(client: TestClient, admin_password: str) -> None:
    rate_limiter._events.clear()  # noqa: SLF001
    login = client.post("/api/auth/admin/login", json={"password": admin_password})
    assert login.status_code == 200
    hostile = client.post(
        "/api/assessments",
        json={
            "team_name": "X",
            "product_service_name": "Y",
            "owner_name": "Z",
            "owner_email": "z@example.com",
            "lookback_days": 90,
        },
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert hostile.status_code == 403
