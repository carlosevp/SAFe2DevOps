from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
import pytest

from app.core.errors import AppError
from app.integrations.http import (
    join_integration_url,
    normalize_ado_org_url,
    normalize_jira_site_url,
    sanitize_remote_text,
)
from app.integrations.jira.adf import adf_to_plain_text
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


def _patch_client(monkeypatch: pytest.MonkeyPatch, transport: _Transport):
    def fake_client(base_url, headers, fn, timeout=None, auth=None):
        with httpx.Client(
            base_url=base_url, headers=headers, auth=auth, transport=transport
        ) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    return fake_client


def _auth_pair(request: httpx.Request) -> tuple[str, str]:
    header = request.headers.get("Authorization", "")
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.split(" ", 1)[1].encode("ascii")).decode("utf-8")
    email, token = decoded.split(":", 1)
    return email, token


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


def test_join_integration_url_preserves_gateway_prefix() -> None:
    base = "https://api.atlassian.com/ex/jira/11111111-1111-1111-1111-111111111111"
    assert (
        join_integration_url(base, "/rest/api/3/myself")
        == "https://api.atlassian.com/ex/jira/11111111-1111-1111-1111-111111111111/rest/api/3/myself"
    )
    # RFC-style joiners discard the prefix; our helper must not.
    assert urljoin(base, "/rest/api/3/myself") == "https://api.atlassian.com/rest/api/3/myself"


def test_classic_myself_url_and_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(lambda req: _json_response({"displayName": "Svc"}))
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="classic-token",
        credential_mode=JIRA_CREDENTIAL_CLASSIC,
    )
    result = provider.test_connection()
    assert result["ok"] is True
    assert str(transport.calls[0].url) == "https://claimsco.atlassian.net/rest/api/3/myself"
    email, token = _auth_pair(transport.calls[0])
    assert email == "svc@example.com"
    assert token == "classic-token"


def test_classic_project_search_matches_curl_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror: curl --request GET --url '.../rest/api/3/project/search' --user 'email:token'."""
    transport = _Transport(
        lambda req: _json_response(
            {
                "startAt": 0,
                "maxResults": 50,
                "total": 1,
                "isLast": True,
                "values": [{"id": "1", "key": "CLAIM", "name": "Claims"}],
            }
        )
    )
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://myprg.atlassian.net",
        email="myemail@example.com",
        api_token="myPAT",
        credential_mode=JIRA_CREDENTIAL_CLASSIC,
    )
    assert provider.api_base == "https://myprg.atlassian.net"
    projects = provider.list_projects()
    assert projects[0].key == "CLAIM"
    req = transport.calls[0]
    assert req.method == "GET"
    assert str(req.url).startswith("https://myprg.atlassian.net/rest/api/3/project/search")
    assert "api.atlassian.com" not in str(req.url)
    email, token = _auth_pair(req)
    assert email == "myemail@example.com"
    assert token == "myPAT"
    assert req.headers.get("Accept") == "application/json"
    assert req.headers.get("Content-Type") is None


def test_scoped_myself_url_and_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    cloud_id = "11111111-1111-1111-1111-111111111111"

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/_edge/tenant_info"):
            return _json_response({"cloudId": cloud_id})
        return _json_response({"displayName": "Scoped Svc"})

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="scoped-token",
        credential_mode=JIRA_CREDENTIAL_SCOPED,
        cloud_id=cloud_id,
    )
    result = provider.test_connection()
    assert result["ok"] is True
    myself = [c for c in transport.calls if str(c.url).endswith("/rest/api/3/myself")]
    assert myself
    assert (
        str(myself[0].url)
        == f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/myself"
    )
    email, token = _auth_pair(myself[0])
    assert email == "svc@example.com"
    assert token == "scoped-token"
    assert "scoped-token" not in result["display_name"]
    assert "Authorization" not in json.dumps(result)


def test_cloud_id_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/_edge/tenant_info"):
            return _json_response({"cloudId": "22222222-2222-2222-2222-222222222222"})
        return _json_response({"displayName": "x"})

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="scoped-token",
        credential_mode=JIRA_CREDENTIAL_SCOPED,
        cloud_id="11111111-1111-1111-1111-111111111111",
    )
    with pytest.raises(AppError) as exc:
        provider.test_connection()
    assert exc.value.code == "jira_cloud_id_mismatch"


def test_cloud_id_discovery_and_invalid_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(
        lambda req: _json_response({"cloudId": "11111111-1111-1111-1111-111111111111"})
    )
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="scoped-token",
        credential_mode=JIRA_CREDENTIAL_SCOPED,
        cloud_id="11111111-1111-1111-1111-111111111111",
    )
    assert provider.discover_cloud_id() == "11111111-1111-1111-1111-111111111111"

    transport.handler = lambda req: _json_response({"cloudId": "not-a-uuid"})
    assert provider.discover_cloud_id() is None

    with pytest.raises(AppError) as exc:
        LiveJiraProvider(
            site_url="https://claimsco.atlassian.net",
            email="svc@example.com",
            api_token="scoped-token",
            credential_mode=JIRA_CREDENTIAL_SCOPED,
            cloud_id="bad-id",
        )
    assert exc.value.code == "jira_cloud_id_required"


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (404, "not_found_or_wrong_base"),
        (429, "throttled"),
    ],
)
def test_identity_http_error_categories(
    monkeypatch: pytest.MonkeyPatch, status: int, category: str
) -> None:
    transport = _Transport(lambda req: httpx.Response(status, text="denied"))
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    with pytest.raises(AppError) as exc:
        provider.test_connection()
    assert exc.value.details["error_category"] == category
    assert "token" not in exc.value.message
    assert "Authorization" not in json.dumps(exc.value.details)


def test_network_or_tls_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class BoomTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("tls handshake failed", request=request)

    transport = BoomTransport()

    def fake_client(base_url, headers, fn, timeout=None, auth=None):
        with httpx.Client(
            base_url=base_url, headers=headers, auth=auth, transport=transport
        ) as client:
            return fn(client)

    monkeypatch.setattr("app.integrations.jira.client.with_client", fake_client)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    with pytest.raises(AppError) as exc:
        provider.test_connection()
    assert exc.value.code == "integration_unreachable"
    assert exc.value.details["error_category"] == "network_or_tls_failure"


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
    _patch_client(monkeypatch, transport)
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


def test_board_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        {
            "startAt": 0,
            "maxResults": 50,
            "total": 3,
            "isLast": False,
            "values": [{"id": 21, "name": "Board A"}],
        },
        {
            "startAt": 1,
            "maxResults": 50,
            "total": 3,
            "isLast": False,
            "values": [{"id": None, "name": "Bad"}, {"id": 22, "name": "Board B"}],
        },
        {
            "startAt": 3,
            "maxResults": 50,
            "total": 3,
            "isLast": True,
            "values": [],
        },
    ]
    state = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        idx = min(state["i"], len(pages) - 1)
        state["i"] += 1
        return _json_response(pages[idx])

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    boards = provider.list_boards("CLAIM")
    assert [b.id for b in boards] == ["21", "22"]
    assert "None" not in [b.id for b in boards]
    assert state["i"] >= 2


def test_enhanced_jql_uses_next_page_token_not_legacy_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode()) if req.content else {}
        bodies.append(body)
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
                            "description": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "ADF body"},
                                            {"type": "hardBreak"},
                                            {"type": "text", "text": "line2"},
                                        ],
                                    }
                                ],
                            },
                        },
                        "changelog": {
                            "histories": [
                                {
                                    "items": [
                                        {
                                            "field": "status",
                                            "fromString": "Done",
                                            "toString": "Reopened",
                                        }
                                    ]
                                }
                            ]
                        },
                    }
                ],
                "nextPageToken": "t2",
                "isLast": False,
            }
        )

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
        acceptance_criteria_field_id="customfield_10010",
    )
    issues = provider.search_issues(
        project_key="CLAIM",
        lookback_days=30,
        page_size=1,
        jql='labels = "safe"',
    )
    assert len(issues) == 1
    assert all(str(c.url).endswith("/rest/api/3/search/jql") for c in transport.calls)
    assert not any(str(c.url).rstrip("/").endswith("/search") for c in transport.calls)
    assert bodies[0]["jql"] == '(labels = "safe") AND project = "CLAIM" AND created >= -30d'
    assert "customfield_10010" in bodies[0]["fields"]
    assert "ADF body" in (issues[0].description or "")
    assert issues[0].acceptance_criteria is None
    assert issues[0].reopened is True
    assert issues[0].created.tzinfo is not None
    assert issues[0].created == datetime(2026, 7, 1, tzinfo=UTC)


def test_repeated_next_page_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "issues": [
                    {
                        "key": "CLAIM-1",
                        "fields": {
                            "summary": "x",
                            "issuetype": {"name": "Story"},
                            "status": {"name": "To Do"},
                            "created": "2026-07-01T00:00:00.000+0000",
                        },
                    }
                ],
                "nextPageToken": "same",
                "isLast": False,
            }
        )

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    with pytest.raises(AppError) as exc:
        provider.search_issues(project_key="CLAIM", lookback_days=30, page_size=1)
    assert exc.value.code == "jira_pagination_stalled"


def test_invalid_project_lookback_page_size() -> None:
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    with pytest.raises(AppError) as exc:
        list(provider.iter_issue_pages(project_key="bad key", lookback_days=30))
    assert exc.value.code == "invalid_jira_project_key"
    with pytest.raises(AppError) as exc:
        list(provider.iter_issue_pages(project_key="CLAIM", lookback_days=0))
    assert exc.value.code == "invalid_jira_lookback_days"
    with pytest.raises(AppError) as exc:
        list(provider.iter_issue_pages(project_key="CLAIM", lookback_days=30, page_size=0))
    assert exc.value.code == "invalid_jira_page_size"


def test_empty_issue_search_counts_as_accessible(monkeypatch: pytest.MonkeyPatch) -> None:
    search_calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/myself"):
            return _json_response({"displayName": "Svc"})
        if req.url.path.endswith("/project/search"):
            return _json_response(
                {
                    "isLast": True,
                    "total": 1,
                    "values": [{"id": "1", "key": "CLAIM", "name": "Claims"}],
                }
            )
        if req.url.path.endswith("/search/jql"):
            search_calls["n"] += 1
            return _json_response({"issues": [], "isLast": True})
        return httpx.Response(404, text="missing")

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    caps = provider.run_capability_checks(project_key="CLAIM", lookback_days=30)
    assert caps.issue_search_accessible is True
    assert search_calls["n"] == 1


def test_capability_check_one_search_request_only(monkeypatch: pytest.MonkeyPatch) -> None:
    search_calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/myself"):
            return _json_response({"displayName": "Svc"})
        if req.url.path.endswith("/project/search"):
            return _json_response(
                {
                    "isLast": True,
                    "values": [{"id": "1", "key": "CLAIM", "name": "Claims"}],
                }
            )
        if req.url.path.endswith("/search/jql"):
            search_calls["n"] += 1
            return _json_response(
                {
                    "issues": [
                        {
                            "key": "CLAIM-1",
                            "fields": {
                                "summary": "x",
                                "issuetype": {"name": "Story"},
                                "status": {"name": "To Do"},
                                "created": "2026-07-01T00:00:00.000+0000",
                            },
                        }
                    ],
                    "nextPageToken": "more",
                    "isLast": False,
                }
            )
        return httpx.Response(500, text="nope")

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    caps = provider.run_capability_checks()
    assert caps.issue_search_accessible is True
    assert search_calls["n"] == 1


def test_malformed_issue_and_naive_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "issues": [
                    {"key": "CLAIM-1", "fields": "bad"},
                    {
                        "key": "CLAIM-2",
                        "fields": {
                            "summary": "ok",
                            "issuetype": {"name": "Bug"},
                            "status": {"name": "To Do"},
                            "created": "not-a-date",
                        },
                    },
                    {
                        "key": "CLAIM-3",
                        "fields": {
                            "summary": "naive",
                            "issuetype": {"name": "Bug"},
                            "status": {"name": "To Do"},
                            "created": "2026-07-01T12:00:00.000",
                            "description": {"type": "doc", "content": []},
                        },
                    },
                ],
                "isLast": True,
            }
        )

    transport = _Transport(handler)
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    issues = provider.search_issues(project_key="CLAIM", lookback_days=30)
    assert [i.key for i in issues] == ["CLAIM-3"]
    assert issues[0].created.tzinfo is not None
    assert issues[0].reopened is None


def test_adf_and_sanitize_do_not_emit_dict_repr() -> None:
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {"type": "unsupportedNode", "content": [{"type": "text", "text": "x"}]},
        ],
    }
    text = adf_to_plain_text(adf)
    assert "Hello" in text
    assert "dict" not in text
    assert sanitize_remote_text(adf) == ""
    assert "{" not in sanitize_remote_text({"a": 1})


def test_no_secrets_in_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    transport = _Transport(lambda req: httpx.Response(401, text="unauthorized token=super-secret"))
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="super-secret-token",
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AppError):
            provider.test_connection()
    blob = "\n".join(r.message for r in caplog.records)
    assert "super-secret-token" not in blob
    assert "Authorization" not in blob or "***REDACTED***" in blob


def test_malformed_project_response(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(lambda req: _json_response(["not", "an", "object"]))
    _patch_client(monkeypatch, transport)
    provider = LiveJiraProvider(
        site_url="https://claimsco.atlassian.net",
        email="svc@example.com",
        api_token="token",
    )
    with pytest.raises(AppError) as exc:
        provider.list_projects()
    assert exc.value.code == "integration_http_error"
