from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

from app.core.errors import AppError
from app.integrations.http import (
    normalize_jira_site_url,
    request_json,
    sanitize_host,
    sanitize_remote_text,
    validate_https_url,
    with_client,
)
from app.integrations.jira.types import (
    JIRA_CREDENTIAL_CLASSIC,
    JIRA_CREDENTIAL_MODES,
    JIRA_CREDENTIAL_SCOPED,
    JiraBoard,
    JiraCapabilityResult,
    JiraIssue,
    JiraProject,
)

_CLOUD_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


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

    def run_capability_checks(
        self, *, project_key: str | None = None, lookback_days: int = 30
    ) -> JiraCapabilityResult: ...


class LiveJiraProvider:
    """Reusable Jira Cloud REST client (classic site or scoped gateway)."""

    def __init__(
        self,
        *,
        site_url: str,
        email: str,
        api_token: str,
        credential_mode: str = JIRA_CREDENTIAL_CLASSIC,
        cloud_id: str | None = None,
        integration_config_id: str | None = None,
    ) -> None:
        mode = (credential_mode or JIRA_CREDENTIAL_CLASSIC).strip()
        if mode not in JIRA_CREDENTIAL_MODES:
            raise AppError(
                code="invalid_jira_credential_mode",
                message="Jira credential mode must be classic_account_api_token or "
                "scoped_service_account_token",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
        self.site_url = normalize_jira_site_url(site_url)
        self.email = (email or "").strip()
        self.api_token = api_token
        self.credential_mode = mode
        self.cloud_id = (cloud_id or "").strip() or None
        self.integration_config_id = integration_config_id
        if not self.email:
            raise AppError(
                code="jira_not_configured",
                message="Jira service/account email is required",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
        if not self.api_token:
            raise AppError(
                code="jira_not_configured",
                message="Jira API token is required",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
        self.api_base = self._resolve_api_base()

    def _resolve_api_base(self) -> str:
        if self.credential_mode == JIRA_CREDENTIAL_CLASSIC:
            return self.site_url
        if not self.cloud_id:
            self.cloud_id = self.discover_cloud_id()
        if not self.cloud_id or not _CLOUD_ID_RE.match(self.cloud_id):
            raise AppError(
                code="jira_cloud_id_required",
                message="Scoped Jira tokens require a valid cloudId for the Atlassian gateway",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
        base = f"https://api.atlassian.com/ex/jira/{self.cloud_id}"
        return validate_https_url(base, label="Jira API gateway", allow_api_gateway=True)

    def discover_cloud_id(self) -> str | None:
        """Best-effort cloudId discovery from the configured site."""

        def _call(client):
            # Public edge endpoint used by Atlassian tenants; no secrets in path.
            return request_json(
                client,
                "GET",
                "/_edge/tenant_info",
                provider="jira",
                operation="discover_cloud_id",
                endpoint_template="/_edge/tenant_info",
                integration_config_id=self.integration_config_id,
            )

        try:
            data = with_client(self.site_url, {"Accept": "application/json"}, _call)
        except AppError:
            return None
        cloud_id = str((data or {}).get("cloudId") or (data or {}).get("cloud_id") or "").strip()
        return cloud_id or None

    def validate_cloud_id_belongs_to_site(self) -> bool:
        if self.credential_mode != JIRA_CREDENTIAL_SCOPED or not self.cloud_id:
            return True
        discovered = self.discover_cloud_id()
        if not discovered:
            # Cannot validate without edge info; allow admin override.
            return True
        if discovered.lower() != self.cloud_id.lower():
            raise AppError(
                code="jira_cloud_id_mismatch",
                message="The configured cloudId does not belong to the configured Jira site",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
        return True

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        operation: str,
        page_number: int | None = None,
        endpoint_template: str | None = None,
    ) -> Any:
        def _call(client):
            return request_json(
                client,
                method,
                path,
                params=params,
                json_body=json_body,
                provider="jira",
                operation=operation,
                endpoint_template=endpoint_template or path,
                integration_config_id=self.integration_config_id,
                page_number=page_number,
            )

        return with_client(self.api_base, self._headers(), _call)

    def test_connection(self) -> dict[str, Any]:
        if self.credential_mode == JIRA_CREDENTIAL_SCOPED:
            self.validate_cloud_id_belongs_to_site()
        data = self._request(
            "GET",
            "/rest/api/3/myself",
            operation="identity_check",
            endpoint_template="/rest/api/3/myself",
        )
        return {
            "ok": True,
            "display_name": sanitize_remote_text((data or {}).get("displayName", "unknown")),
            "site_url": self.site_url,
            "api_base": self.api_base,
            "credential_mode": self.credential_mode,
            "cloud_id": self.cloud_id,
            "resolved_api_host": sanitize_host(self.api_base),
        }

    def list_projects(self) -> list[JiraProject]:
        projects: dict[str, JiraProject] = {}
        start_at = 0
        page_size = 50
        page_number = 1
        while True:
            data = self._request(
                "GET",
                "/rest/api/3/project/search",
                params={
                    "maxResults": page_size,
                    "startAt": start_at,
                    "orderBy": "key",
                },
                operation="project_catalog",
                page_number=page_number,
                endpoint_template="/rest/api/3/project/search",
            )
            values = (data or {}).get("values") or []
            for item in values:
                project_id = str(item.get("id") or "")
                if not project_id or project_id in projects:
                    continue
                projects[project_id] = JiraProject(
                    key=sanitize_remote_text(item.get("key")),
                    name=sanitize_remote_text(item.get("name")),
                    id=project_id,
                    project_type_key=sanitize_remote_text(item.get("projectTypeKey")) or None,
                    style=sanitize_remote_text(item.get("style")) or None,
                )
            is_last = bool((data or {}).get("isLast"))
            total = int((data or {}).get("total") or 0)
            start_at += len(values)
            if is_last or not values or (total and start_at >= total):
                break
            page_number += 1
            if page_number > 100:
                break
        return sorted(projects.values(), key=lambda p: (p.key.lower(), p.name.lower()))

    def list_boards(self, project_key: str) -> list[JiraBoard]:
        data = self._request(
            "GET",
            "/rest/agile/1.0/board",
            params={"projectKeyOrId": project_key, "maxResults": 50},
            operation="list_boards",
            endpoint_template="/rest/agile/1.0/board",
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
        """Enhanced JQL search with nextPageToken pagination (not legacy /search)."""
        safe_key = project_key.replace('"', "")
        base_jql = (
            jql.strip()
            if jql
            else f'project = "{safe_key}" AND created >= -{int(lookback_days)}d'
        )
        next_page_token: str | None = None
        page_number = 1
        fields = [
            "summary",
            "issuetype",
            "status",
            "created",
            "resolutiondate",
            "description",
        ]
        while True:
            body: dict[str, Any] = {
                "jql": base_jql,
                "maxResults": page_size,
                "fields": fields,
                "expand": "changelog",
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            data = self._request(
                "POST",
                "/rest/api/3/search/jql",
                json_body=body,
                operation="issue_search",
                page_number=page_number,
                endpoint_template="/rest/api/3/search/jql",
            )
            raw_issues = (data or {}).get("issues") or []
            page: list[JiraIssue] = []
            for item in raw_issues:
                fields_obj = item.get("fields") or {}
                created = _parse_dt(fields_obj.get("created"))
                resolved = _parse_dt(fields_obj.get("resolutiondate"))
                page.append(
                    JiraIssue(
                        key=sanitize_remote_text(item.get("key")),
                        issue_type=sanitize_remote_text(
                            (fields_obj.get("issuetype") or {}).get("name", "Unknown")
                        ),
                        status=sanitize_remote_text(
                            (fields_obj.get("status") or {}).get("name", "Unknown")
                        ),
                        created=created or datetime.now(UTC),
                        resolved=resolved,
                        summary=sanitize_remote_text(fields_obj.get("summary")),
                        acceptance_criteria=sanitize_remote_text(fields_obj.get("description"))
                        or None,
                        reopened=False,
                        changelog=_extract_changelog(item.get("changelog") or {}),
                    )
                )
            yield page
            next_page_token = (data or {}).get("nextPageToken")
            is_last = bool((data or {}).get("isLast"))
            if is_last or not next_page_token or not raw_issues:
                break
            page_number += 1
            if page_number > 200:
                break

    def run_capability_checks(
        self, *, project_key: str | None = None, lookback_days: int = 30
    ) -> JiraCapabilityResult:
        result = JiraCapabilityResult(
            configured=True,
            credentials_decryptable=True,
            credential_mode=self.credential_mode,
            cloud_id_present=bool(self.cloud_id),
            resolved_api_host=sanitize_host(self.api_base),
        )
        try:
            identity = self.test_connection()
            result.identity_authenticated = True
            result.display_name = identity.get("display_name")
        except AppError as exc:
            result.last_error_category = (exc.details or {}).get("error_category") or exc.code
            result.last_error_message = exc.message
            result.corrective_action = _jira_corrective(result.last_error_category)
            return result

        try:
            projects = self.list_projects()
            result.project_catalog_accessible = True
            result.visible_project_count = len(projects)
            if not projects:
                result.last_error_category = "no_visible_projects"
                result.last_error_message = (
                    "Jira accepted the credentials, but this account cannot see any projects. "
                    "Verify Browse Projects permission for the Jira service account."
                )
                result.corrective_action = (
                    "Grant Browse Projects (and View Issues) to the service account, "
                    "or select a different account with project visibility."
                )
        except AppError as exc:
            result.last_error_category = (exc.details or {}).get("error_category") or exc.code
            result.last_error_message = exc.message
            result.corrective_action = _jira_corrective(result.last_error_category)
            return result

        probe_key = project_key or (projects[0].key if projects else None)
        if probe_key:
            try:
                pages = list(
                    self.iter_issue_pages(
                        project_key=probe_key, lookback_days=min(lookback_days, 30), page_size=1
                    )
                )
                _ = pages  # touch
                result.issue_search_accessible = True
            except AppError as exc:
                result.issue_search_accessible = False
                result.last_error_category = (exc.details or {}).get("error_category") or exc.code
                result.last_error_message = exc.message
                result.corrective_action = (
                    "Credentials can list projects, but issue search failed. "
                    "Verify View Issues permission and scoped token scopes for JQL search."
                )
        else:
            result.issue_search_accessible = None
        return result


def _jira_corrective(category: str | None) -> str:
    mapping = {
        "authentication_failed": "Re-check email/token and credential mode (classic vs scoped).",
        "permission_denied": "Grant Browse Projects / View Issues (and required token scopes).",
        "not_found_or_wrong_base": "Verify site URL, credential mode, and cloudId for scoped tokens.",
        "throttled": "Jira is rate-limiting requests; retry shortly.",
        "network_timeout": "Outbound HTTPS to Jira timed out; check proxy/DNS/firewall.",
        "network_or_tls_failure": "TLS/network failure reaching Jira; verify corporate CA and proxy.",
        "jira_cloud_id_required": "Enter the Jira cloudId for scoped service-account tokens.",
        "jira_cloud_id_mismatch": "Correct the cloudId so it matches the configured site.",
        "no_visible_projects": "Grant Browse Projects to the service account.",
    }
    return mapping.get(category or "", "Review Jira configuration and retry diagnostics.")


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


def quote_project_key(project_key: str) -> str:
    return quote(project_key, safe="")
