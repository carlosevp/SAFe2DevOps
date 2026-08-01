from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.errors import AppError
from app.integrations.http import normalize_ado_org_url, normalize_jira_site_url
from app.integrations.jira.client import LiveJiraProvider
from app.integrations.jira.types import JIRA_CREDENTIAL_CLASSIC, JIRA_CREDENTIAL_SCOPED


class _Transport(httpx.BaseTransport):
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def _json_response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def test_normalize_jira_rejects_rest_path() -> None:
    with pytest.raises(AppError) as exc:
        normalize_jira_site_url("https://claimsco.atlassian.net/rest/api/3")
    assert exc.value.code == "invalid_integration_url"


def test_normalize_ado_org_name_and_url() -> None:
    assert normalize_ado_org_url("claimsco") == "https://dev.azure.com/claimsco"
    assert normalize_ado_org_url("https://dev.azure.com/claimsco/") == "https://dev.azure.com/claimsco"
    assert (
        normalize_ado_org_url("https://claimsco.visualstudio.com") == "https://dev.azure.com/claimsco"
    )


def test_classic_myself_and_project_search(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(
        lambda req: _json_response(
            {"displayName": "Svc"}
            if req.url.path.endswith("/myself")
            else {
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
                "isLast": True,
                "values": [{"id": "1", "key": "CLAIM", "name": "Claims", "projectTypeKey": "software"}],
            }
        )
    )

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="classic-token",
        credential_mode=JIRA_CREDENTIAL_CLASSIC,
    )
    assert provider.test_connection()["ok"] is True
    projects = provider.list_projects()
    assert projects[0].key == "CLAIM"
    assert any(c.url.path.endswith("/project/search") for c in transport.calls)
    assert not any("/rest/api/3/project'" in str(c.url) for c in transport.calls)


def test_scoped_uses_gateway_and_cloud_id(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(
        lambda req: _json_response(
            {"cloudId": "11111111-1111-1111-1111-111111111111"}
            if req.url.path.endswith("/_edge/tenant_info")
            else {"displayName": "Scoped Svc"}
        )
    )

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="scoped-token",
        credential_mode=JIRA_CREDENTIAL_SCOPED,
        cloud_id="11111111-1111-1111-1111-111111111111",
    )
    assert "api.atlassian.com/ex/jira/11111111-1111-1111-1111-111111111111" in provider.api_base
    result = provider.test_connection()
    assert result["ok"] is True
    assert result["resolved_api_host"] == "api.atlassian.com"


def test_project_pagination_and_zero_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        {
            "startAt": 0,
            "maxResults": 1,
            "total": 2,
            "isLast": False,
            "values": [{"id": "1", "key": "A", "name": "Alpha"}],
        },
        {
            "startAt": 1,
            "maxResults": 1,
            "total": 2,
            "isLast": True,
            "values": [{"id": "2", "key": "B", "name": "Beta"}],
        },
    ]
    state = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/myself"):
            return _json_response({"displayName": "Svc"})
        idx = min(state["i"], len(pages) - 1)
        state["i"] += 1
        return _json_response(pages[idx])

    transport = _Transport(handler)

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    projects = provider.list_projects()
    assert [p.key for p in projects] == ["A", "B"]

    state["i"] = 0
    pages[:] = [{"startAt": 0, "maxResults": 50, "total": 0, "isLast": True, "values": []}]
    caps = provider.run_capability_checks()
    assert caps.identity_authenticated is True
    assert caps.visible_project_count == 0
    assert caps.last_error_category == "no_visible_projects"


def test_enhanced_jql_uses_next_page_token_not_legacy_search(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.method} {req.url.path}")
        body = json.loads(req.content.decode()) if req.content else {}
        if body.get("nextPageToken") == "t2":
            return _json_response({"issues": [], "isLast": True})
        return _json_response(
            {
                "issues": [
                    {
                        "key": "CLAIM-1",
                        "fields": {
                            "summary": "x",
                            "issuetype": {"name": "Story"},
                            "status": {"name": "Done"},
                            "created": "2026-07-01T00:00:00.000+0000",
                            "resolutiondate": "2026-07-02T00:00:00.000+0000",
                            "description": None,
                        },
                    }
                ],
                "nextPageToken": "t2",
                "isLast": False,
            }
        )

    transport = _Transport(handler)

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    issues = provider.search_issues(project_key="CLAIM", lookback_days=30, page_size=1)
    assert len(issues) == 1
    assert all("/search/jql" in c for c in calls)
    assert not any(c.endswith("/search") for c in calls)


def test_401_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(lambda req: httpx.Response(401, text="unauthorized"))

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="bad",
    )
    with pytest.raises(AppError) as exc:
        provider.test_connection()
    assert exc.value.details["error_category"] == "authentication_failed"
