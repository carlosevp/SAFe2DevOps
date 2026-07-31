from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from app.integrations.http import (
    request_json,
    sanitize_remote_text,
    validate_https_url,
    with_client,
)
from app.integrations.jira.types import JiraBoard, JiraIssue, JiraProject


class JiraProvider(Protocol):
    def test_connection(self) -> dict[str, Any]: ...

    def list_projects(self) -> list[JiraProject]: ...

    def list_boards(self, project_key: str) -> list[JiraBoard]: ...

    def search_issues(
        self,
        *,
        project_key: str,
        lookback_days: int,
        jql: str | None = None,
        page_size: int = 50,
    ) -> list[JiraIssue]: ...

    def iter_issue_pages(
        self,
        *,
        project_key: str,
        lookback_days: int,
        jql: str | None = None,
        page_size: int = 50,
    ): ...


class LiveJiraProvider:
    """Jira Cloud REST adapter (read-only)."""

    def __init__(self, *, site_url: str, email: str, api_token: str) -> None:
        self.site_url = validate_https_url(site_url, label="Jira site URL")
        self.email = email
        self.api_token = api_token

    def _headers(self) -> dict[str, str]:
        import base64

        token = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def test_connection(self) -> dict[str, Any]:
        def _call(client):
            data = request_json(client, "GET", "/rest/api/3/myself")
            return {
                "ok": True,
                "display_name": sanitize_remote_text((data or {}).get("displayName", "unknown")),
                "site_url": self.site_url,
            }

        return with_client(self.site_url, self._headers(), _call)

    def list_projects(self) -> list[JiraProject]:
        def _call(client):
            data = request_json(
                client, "GET", "/rest/api/3/project/search", params={"maxResults": 100}
            )
            values = (data or {}).get("values") or []
            return [
                JiraProject(
                    key=sanitize_remote_text(item.get("key")),
                    name=sanitize_remote_text(item.get("name")),
                    id=str(item.get("id")),
                )
                for item in values
            ]

        return with_client(self.site_url, self._headers(), _call)

    def list_boards(self, project_key: str) -> list[JiraBoard]:
        def _call(client):
            data = request_json(
                client,
                "GET",
                "/rest/agile/1.0/board",
                params={"projectKeyOrId": project_key, "maxResults": 50},
            )
            values = (data or {}).get("values") or []
            return [
                JiraBoard(
                    id=str(item.get("id")),
                    name=sanitize_remote_text(item.get("name")),
                    project_key=project_key,
                )
                for item in values
            ]

        return with_client(self.site_url, self._headers(), _call)

    def search_issues(
        self,
        *,
        project_key: str,
        lookback_days: int,
        jql: str | None = None,
        page_size: int = 50,
    ) -> list[JiraIssue]:
        issues: list[JiraIssue] = []
        for page in self.iter_issue_pages(
            project_key=project_key, lookback_days=lookback_days, jql=jql, page_size=page_size
        ):
            issues.extend(page)
        return issues

    def iter_issue_pages(
        self,
        *,
        project_key: str,
        lookback_days: int,
        jql: str | None = None,
        page_size: int = 50,
    ):
        base_jql = (
            jql.strip()
            if jql
            else f'project = "{project_key}" AND created >= -{int(lookback_days)}d'
        )
        start_at = 0

        def _page(client, start: int):
            return request_json(
                client,
                "GET",
                "/rest/api/3/search",
                params={
                    "jql": base_jql,
                    "startAt": start,
                    "maxResults": page_size,
                    "fields": "summary,issuetype,status,created,resolutiondate,description,customfield_10000",
                    "expand": "changelog",
                },
            )

        while True:
            data = with_client(self.site_url, self._headers(), lambda c, s=start_at: _page(c, s))
            raw_issues = (data or {}).get("issues") or []
            page: list[JiraIssue] = []
            for item in raw_issues:
                fields = item.get("fields") or {}
                created = _parse_dt(fields.get("created"))
                resolved = _parse_dt(fields.get("resolutiondate"))
                page.append(
                    JiraIssue(
                        key=sanitize_remote_text(item.get("key")),
                        issue_type=sanitize_remote_text(
                            (fields.get("issuetype") or {}).get("name", "Unknown")
                        ),
                        status=sanitize_remote_text(
                            (fields.get("status") or {}).get("name", "Unknown")
                        ),
                        created=created or datetime.now(UTC),
                        resolved=resolved,
                        summary=sanitize_remote_text(fields.get("summary")),
                        acceptance_criteria=sanitize_remote_text(fields.get("description")) or None,
                        reopened=False,
                        changelog=_extract_changelog(item.get("changelog") or {}),
                    )
                )
            yield page
            start_at += len(raw_issues)
            total = int((data or {}).get("total") or 0)
            if start_at >= total or not raw_issues:
                break


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_changelog(changelog: dict[str, Any]) -> list[dict[str, Any]]:
    histories = changelog.get("histories") or []
    events: list[dict[str, Any]] = []
    for history in histories[:20]:
        for item in history.get("items") or []:
            events.append(
                {
                    "field": sanitize_remote_text(item.get("field")),
                    "from": sanitize_remote_text(item.get("fromString")),
                    "to": sanitize_remote_text(item.get("toString")),
                }
            )
    return events
