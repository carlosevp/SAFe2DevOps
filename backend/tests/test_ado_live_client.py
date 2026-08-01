from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.errors import AppError
from app.integrations.ado.client import LiveAdoProvider


class _Transport(httpx.BaseTransport):
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


def _json(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def test_ado_project_repo_pipeline_and_encoded_names(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/_apis/projects"):
            return _json(
                {
                    "count": 2,
                    "value": [
                        {"id": "p1", "name": "Claims Co"},
                        {"id": "p space", "name": "Special Project"},
                    ],
                }
            )
        if "/_apis/git/repositories" in path and path.count("/") >= 4:
            return _json({"value": [{"id": "r1", "name": "claims-api", "defaultBranch": "refs/heads/main"}]})
        if path.endswith("/_apis/pipelines"):
            return _json({"value": [{"id": "pl1", "name": "claims-api-CI"}]})
        return _json({"value": []})

    transport = _Transport(handler)

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.ado.client.with_client", fake_client)
    provider = LiveAdoProvider(org_url="claimsco", pat="pat-value")
    assert provider.org_url == "https://dev.azure.com/claimsco"
    projects = provider.list_projects()
    assert len(projects) == 2
    repos = provider.list_repositories("p space")
    assert repos[0].name == "claims-api"
    assert any("%20" in str(c.url) or "p%20space" in str(c.url) for c in transport.calls)
    pipelines = provider.list_pipelines("p1")
    assert pipelines[0].id == "pl1"
    caps = provider.run_capability_checks()
    assert caps.project_catalog_accessible is True
    assert caps.repository_catalog_accessible is True
    assert caps.pipeline_catalog_accessible is True


def test_ado_missing_code_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/_apis/projects"):
            return _json({"value": [{"id": "p1", "name": "Claims Co"}]})
        if "/git/repositories" in req.url.path:
            return httpx.Response(403, text="TF400813")
        return _json({"value": []})

    transport = _Transport(handler)

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.ado.client.with_client", fake_client)
    provider = LiveAdoProvider(org_url="https://dev.azure.com/claimsco", pat="pat")
    caps = provider.run_capability_checks()
    assert caps.project_catalog_accessible is True
    assert caps.repository_catalog_accessible is False
    assert caps.last_error_category == "missing_code_scope"


def test_ado_expired_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(lambda req: httpx.Response(401, text="expired"))

    def fake_client(base_url, headers, fn, timeout=None):
        with httpx.Client(base_url=base_url, headers=headers, transport=transport) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.ado.client.with_client", fake_client)
    provider = LiveAdoProvider(org_url="https://dev.azure.com/claimsco", pat="old")
    with pytest.raises(AppError) as exc:
        provider.list_projects()
    assert exc.value.details["error_category"] == "authentication_failed"
