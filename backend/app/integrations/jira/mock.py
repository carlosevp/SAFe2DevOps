from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.integrations.http import sanitize_remote_text
from app.integrations.jira.types import (
    JIRA_CREDENTIAL_CLASSIC,
    JiraBoard,
    JiraCapabilityResult,
    JiraIssue,
    JiraProject,
)


class MockJiraProvider:
    """Deterministic Jira Cloud provider for development, tests, and demos."""

    def __init__(self, *, site_url: str = "https://claimsco.atlassian.net") -> None:
        self.site_url = site_url

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "display_name": "Mock Jira Service Account", "site_url": self.site_url}

    def list_projects(self) -> list[JiraProject]:
        return [
            JiraProject(key="CLAIM", name="Claims Integration", id="10001"),
            JiraProject(key="PORTAL", name="Claims Portal", id="10002"),
            JiraProject(key="INFRA", name="Infrastructure", id="10003"),
        ]

    def list_boards(self, project_key: str) -> list[JiraBoard]:
        if project_key == "CLAIM":
            return [
                JiraBoard(id="21", name="Claims Integration Sprint Board", project_key="CLAIM"),
                JiraBoard(id="22", name="Kanban Board", project_key="CLAIM"),
            ]
        return []

    def search_issues(
        self,
        *,
        project_key: str,
        lookback_days: int,
        jql: str | None = None,
        page_size: int = 50,
    ) -> list[JiraIssue]:
        # Pagination simulation: generate pages of deterministic issues.
        now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        start = now - timedelta(days=lookback_days)
        issues: list[JiraIssue] = []
        total = 67 if project_key == "CLAIM" else 12
        bugs = 11 if project_key == "CLAIM" else 2
        for idx in range(total):
            created = start + timedelta(days=(idx % max(lookback_days, 1)))
            resolved = created + timedelta(days=3 + (idx % 8)) if idx < total - 8 else None
            issue_type = "Bug" if idx < bugs else ("Story" if idx % 3 else "Task")
            summary = f"{project_key} work item {idx + 1}"
            if jql and "ignore previous instructions" in jql.lower():
                summary = sanitize_remote_text(f"{summary} {jql}")
            issues.append(
                JiraIssue(
                    key=f"{project_key}-{1000 + idx}",
                    issue_type=issue_type,
                    status="Done" if resolved else ("In Progress" if idx % 5 == 0 else "To Do"),
                    created=created,
                    resolved=resolved,
                    summary=sanitize_remote_text(summary),
                    description="Mock description" if idx % 3 == 0 else None,
                    acceptance_criteria="Given/When/Then" if idx % 2 == 0 else None,
                    reopened=idx % 17 == 0,
                    changelog=[{"field": "status", "from": "In Progress", "to": "Done"}]
                    if resolved
                    else [],
                    changelog_partial=False,
                )
            )
        # Return in pages for callers that paginate; here we expose full set and page helpers.
        return issues

    def iter_issue_pages(
        self,
        *,
        project_key: str,
        lookback_days: int,
        jql: str | None = None,
        page_size: int = 50,
    ):
        issues = self.search_issues(
            project_key=project_key, lookback_days=lookback_days, jql=jql, page_size=page_size
        )
        for offset in range(0, len(issues), page_size):
            yield issues[offset : offset + page_size]

    def run_capability_checks(
        self, *, project_key: str | None = None, lookback_days: int = 30
    ) -> JiraCapabilityResult:
        projects = self.list_projects()
        return JiraCapabilityResult(
            configured=True,
            credentials_decryptable=True,
            identity_authenticated=True,
            project_catalog_accessible=True,
            issue_search_accessible=True,
            visible_project_count=len(projects),
            resolved_api_host="claimsco.atlassian.net",
            cloud_id_present=False,
            credential_mode=JIRA_CREDENTIAL_CLASSIC,
            display_name="Mock Jira Service Account",
        )
