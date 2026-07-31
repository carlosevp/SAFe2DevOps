from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_login_logout_flow(client: TestClient, admin_password: str) -> None:
    me = client.get("/api/auth/admin/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is False

    bad = client.post("/api/auth/admin/login", json={"password": "wrong-password"})
    assert bad.status_code == 401

    login = client.post("/api/auth/admin/login", json={"password": admin_password})
    assert login.status_code == 200
    assert login.json()["status"] == "authenticated"
    assert "sd_admin_session" in login.cookies

    me_auth = client.get("/api/auth/admin/me")
    assert me_auth.status_code == 200
    assert me_auth.json()["authenticated"] is True
    assert me_auth.json()["role"] == "admin"

    logout = client.post("/api/auth/admin/logout")
    assert logout.status_code == 200
    assert logout.json()["status"] == "logged_out"
