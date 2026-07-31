from __future__ import annotations

from fastapi.testclient import TestClient


def test_spa_fallback_and_api_precedence(client: TestClient) -> None:
    api = client.get("/api/health/live")
    assert api.status_code == 200
    assert api.json()["status"] == "ok"

    # FastAPI SPA fallback only applies to browser navigation Accept headers.
    spa = client.get("/assessments/demo", headers={"Accept": "text/html"})
    assert spa.status_code == 200
    assert "SPA" in spa.text

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow" in robots.text
