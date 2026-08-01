from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_catalog_refresh_and_setup_selectable(client: TestClient) -> None:
    refreshed = client.post("/api/integrations/catalog/refresh")
    assert refreshed.status_code == 200, refreshed.text
    status = client.get("/api/integrations").json()
    assert status["setup_state"]["jira"]["selectable"] is True
    assert status["setup_state"]["ado"]["selectable"] is True
    assert status["setup_state"]["jira"]["availability"] != "administratively_disabled"
    assert status["setup_state"]["ado"]["availability"] != "administratively_disabled"

    jira = client.get("/api/integrations/catalog/jira/projects")
    ado = client.get("/api/integrations/catalog/ado/projects")
    assert jira.status_code == 200
    assert ado.status_code == 200
    assert len(jira.json()) >= 1
    assert len(ado.json()) >= 1


def test_secret_nondisclosure_with_new_fields(client: TestClient) -> None:
    secret = "super-secret-jira-token-xyz"
    ado_secret = "super-secret-ado-pat-xyz"
    save = client.put(
        "/api/integrations/jira",
        json={
            "site_url": "https://claimsco.atlassian.net",
            "service_account_email": "svc@example.com",
            "api_token": secret,
            "credential_mode": "classic_account_api_token",
            "cloud_id": None,
        },
    )
    assert save.status_code == 200, save.text
    ado = client.put(
        "/api/integrations/ado",
        json={"org_url": "claimsco", "pat": ado_secret},
    )
    assert ado.status_code == 200, ado.text
    assert ado.json()["ado_org_url"] == "https://dev.azure.com/claimsco"

    status = client.get("/api/integrations").json()
    dumped = json.dumps(status)
    assert secret not in dumped
    assert ado_secret not in dumped
    assert status["jira_credential_mode"] == "classic_account_api_token"
    assert "jira_capabilities" in status
    assert "ado_capabilities" in status


def test_diagnostics_endpoints(client: TestClient) -> None:
    jira = client.post("/api/integrations/diagnostics/jira")
    ado = client.post("/api/integrations/diagnostics/ado")
    assert jira.status_code == 200, jira.text
    assert ado.status_code == 200, ado.text
    body = jira.json()
    assert body["provider"] == "jira"
    dumped = json.dumps(body)
    assert "Authorization" not in dumped
    assert "scoped-token" not in dumped
    assert body["identity_test"] == "pass"
    assert ado.json()["project_catalog_test"] == "pass"


def test_setup_state_endpoint(client: TestClient) -> None:
    client.post("/api/integrations/catalog/refresh")
    state = client.get("/api/integrations/setup-state")
    assert state.status_code == 200
    body = state.json()
    assert body["jira"]["selectable"] is True
    assert body["ado"]["selectable"] is True
