from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Iterator, Protocol
from urllib.parse import quote

import httpx

from app.core.errors import AppError
from app.integrations.http import (
    join_integration_url,
    normalize_jira_site_url,
    request_json,
    sanitize_host,
    sanitize_remote_text,
    validate_https_url,
    with_client,
)
from app.integrations.jira.adf import adf_to_plain_text
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
_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
_CUSTOM_FIELD_RE = re.compile(r"^customfield_\d+$", re.I)

_MAX_PROJECT_PAGES = 100
_MAX_BOARD_PAGES = 100
_MAX_ISSUE_PAGES = 200
_MIN_PAGE_SIZE = 1
_MAX_PAGE_SIZE = 100
_MIN_LOOKBACK_DAYS = 1
_MAX_LOOKBACK_DAYS = 3650


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
        acceptance_criteria_field_id: str | None = None,
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
        self.acceptance_criteria_field_id = _normalize_ac_field_id(acceptance_criteria_field_id)
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
        if not self.cloud_id or not _CLOUD_ID_RE.fullmatch(self.cloud_id):
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
            # Edge discovery is unauthenticated against the classic site host (no --user).
            data = with_client(self.site_url, {"Accept": "application/json"}, _call)
        except AppError:
            # Network/HTTP discovery failures are best-effort; other exceptions propagate.
            return None
        if not isinstance(data, dict):
            return None
        cloud_id = str(data.get("cloudId") or data.get("cloud_id") or "").strip()
        if not cloud_id or not _CLOUD_ID_RE.fullmatch(cloud_id):
            return None
        return cloud_id

    def validate_cloud_id_belongs_to_site(self) -> bool:
        if self.credential_mode != JIRA_CREDENTIAL_SCOPED or not self.cloud_id:
            return True
        if not _CLOUD_ID_RE.fullmatch(self.cloud_id):
            raise AppError(
                code="jira_cloud_id_required",
                message="Scoped Jira tokens require a valid UUID-shaped cloudId",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
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

    def _auth(self) -> httpx.BasicAuth:
        # Same as curl --user "email:api_token" (HTTP Basic over HTTPS).
        return httpx.BasicAuth(self.email, self.api_token)

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        # Match curl: auth via --user, Accept for JSON; Content-Type only when posting JSON.
        headers = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

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
        # Classic mode: api_base is https://{site}.atlassian.net (same host as working curl).
        # Scoped mode: api_base is https://api.atlassian.com/ex/jira/{cloudId}.
        absolute = join_integration_url(self.api_base, path)

        def _call(client):
            return request_json(
                client,
                method,
                absolute,
                params=params,
                json_body=json_body,
                provider="jira",
                operation=operation,
                endpoint_template=endpoint_template or path,
                integration_config_id=self.integration_config_id,
                page_number=page_number,
            )

        return with_client(
            self.api_base,
            self._headers(json_body=json_body is not None),
            _call,
            auth=self._auth(),
        )

    def test_connection(self) -> dict[str, Any]:
        if self.credential_mode == JIRA_CREDENTIAL_SCOPED:
            self.validate_cloud_id_belongs_to_site()
        data = self._request(
            "GET",
            "/rest/api/3/myself",
            operation="identity_check",
            endpoint_template="/rest/api/3/myself",
        )
        if not isinstance(data, dict):
            raise AppError(
                code="integration_http_error",
                message="Jira identity response was not a JSON object",
                status_code=502,
                details={"error_category": "provider_error", "provider": "jira"},
            )
        return {
            "ok": True,
            "display_name": sanitize_remote_text(data.get("displayName", "unknown")),
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
            if page_number > _MAX_PROJECT_PAGES:
                raise AppError(
                    code="jira_pagination_limit",
                    message=f"Jira project catalog exceeded {_MAX_PROJECT_PAGES} pages",
                    status_code=502,
                    details={"error_category": "pagination_limit", "provider": "jira"},
                )
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
            if not isinstance(data, dict):
                raise AppError(
                    code="integration_http_error",
                    message="Jira project search response was not a JSON object",
                    status_code=502,
                    details={"error_category": "provider_error", "provider": "jira"},
                )
            values = data.get("values")
            if values is None:
                values = []
            if not isinstance(values, list):
                raise AppError(
                    code="integration_http_error",
                    message="Jira project search values were not a list",
                    status_code=502,
                    details={"error_category": "provider_error", "provider": "jira"},
                )
            for item in values:
                if not isinstance(item, dict):
                    continue
                project_id = _as_nonempty_str(item.get("id"))
                key = _as_nonempty_str(item.get("key"))
                if not project_id or not key or project_id in projects:
                    continue
                projects[project_id] = JiraProject(
                    key=sanitize_remote_text(key),
                    name=sanitize_remote_text(item.get("name")),
                    id=project_id,
                    project_type_key=sanitize_remote_text(item.get("projectTypeKey")) or None,
                    style=sanitize_remote_text(item.get("style")) or None,
                )
            is_last = bool(data.get("isLast"))
            total = _safe_nonneg_int(data.get("total"))
            start_at += len(values)
            if is_last or not values or (total is not None and start_at >= total):
                break
            page_number += 1
        return sorted(projects.values(), key=lambda p: (p.key.lower(), p.name.lower()))

    def list_boards(self, project_key: str) -> list[JiraBoard]:
        safe_key = _validate_project_key(project_key)
        boards: dict[str, JiraBoard] = {}
        start_at = 0
        page_size = 50
        page_number = 1
        while True:
            if page_number > _MAX_BOARD_PAGES:
                raise AppError(
                    code="jira_pagination_limit",
                    message=f"Jira board listing exceeded {_MAX_BOARD_PAGES} pages",
                    status_code=502,
                    details={"error_category": "pagination_limit", "provider": "jira"},
                )
            data = self._request(
                "GET",
                "/rest/agile/1.0/board",
                params={
                    "projectKeyOrId": safe_key,
                    "maxResults": page_size,
                    "startAt": start_at,
                },
                operation="list_boards",
                page_number=page_number,
                endpoint_template="/rest/agile/1.0/board",
            )
            if not isinstance(data, dict):
                raise AppError(
                    code="integration_http_error",
                    message="Jira board listing response was not a JSON object",
                    status_code=502,
                    details={"error_category": "provider_error", "provider": "jira"},
                )
            values = data.get("values")
            if values is None:
                values = []
            if not isinstance(values, list):
                raise AppError(
                    code="integration_http_error",
                    message="Jira board listing values were not a list",
                    status_code=502,
                    details={"error_category": "provider_error", "provider": "jira"},
                )
            for item in values:
                if not isinstance(item, dict):
                    continue
                board_id = _as_nonempty_str(item.get("id"))
                if not board_id or board_id in boards:
                    continue
                boards[board_id] = JiraBoard(
                    id=board_id,
                    name=sanitize_remote_text(item.get("name")),
                    project_key=safe_key,
                )
            is_last = bool(data.get("isLast"))
            total = _safe_nonneg_int(data.get("total"))
            start_at += len(values)
            if is_last or not values or (total is not None and start_at >= total):
                break
            page_number += 1
        return sorted(boards.values(), key=lambda b: (b.name.lower(), b.id))

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
    ) -> Iterator[list[JiraIssue]]:
        """Enhanced JQL search with nextPageToken pagination (not legacy /search).

        Caller-provided JQL is combined with project and lookback constraints:
        ``({caller_jql}) AND project = "KEY" AND created >= -Nd``.
        When ``jql`` is omitted, only the project/lookback filter is used.
        """
        safe_key = _validate_project_key(project_key)
        days = _validate_lookback_days(lookback_days)
        size = _validate_page_size(page_size)
        constraints = f'project = "{safe_key}" AND created >= -{days}d'
        caller = (jql or "").strip()
        if caller:
            base_jql = f"({caller}) AND {constraints}"
        else:
            base_jql = constraints

        next_page_token: str | None = None
        seen_tokens: set[str] = set()
        page_number = 1
        fields = [
            "summary",
            "issuetype",
            "status",
            "created",
            "resolutiondate",
            "description",
        ]
        if self.acceptance_criteria_field_id:
            fields.append(self.acceptance_criteria_field_id)

        while True:
            if page_number > _MAX_ISSUE_PAGES:
                raise AppError(
                    code="jira_pagination_limit",
                    message=f"Jira issue search exceeded {_MAX_ISSUE_PAGES} pages",
                    status_code=502,
                    details={"error_category": "pagination_limit", "provider": "jira"},
                )
            body: dict[str, Any] = {
                "jql": base_jql,
                "maxResults": size,
                "fields": fields,
                "expand": "changelog",
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            try:
                data = self._request(
                    "POST",
                    "/rest/api/3/search/jql",
                    json_body=body,
                    operation="issue_search",
                    page_number=page_number,
                    endpoint_template="/rest/api/3/search/jql",
                )
            except AppError as exc:
                if (exc.details or {}).get("status") == 400:
                    raise AppError(
                        code="invalid_jql",
                        message="Jira rejected the issue search JQL",
                        status_code=400,
                        details={
                            "error_category": "invalid_jql",
                            "provider": "jira",
                            "operation": "issue_search",
                        },
                    ) from exc
                raise
            if not isinstance(data, dict):
                raise AppError(
                    code="integration_http_error",
                    message="Jira issue search response was not a JSON object",
                    status_code=502,
                    details={"error_category": "provider_error", "provider": "jira"},
                )
            raw_issues = data.get("issues")
            if raw_issues is None:
                raw_issues = []
            if not isinstance(raw_issues, list):
                raise AppError(
                    code="integration_http_error",
                    message="Jira issue search issues were not a list",
                    status_code=502,
                    details={"error_category": "provider_error", "provider": "jira"},
                )
            page: list[JiraIssue] = []
            for item in raw_issues:
                parsed = _parse_issue(
                    item, acceptance_criteria_field_id=self.acceptance_criteria_field_id
                )
                if parsed is not None:
                    page.append(parsed)
            yield page

            token_raw = data.get("nextPageToken")
            next_page_token = str(token_raw).strip() if token_raw else None
            is_last = bool(data.get("isLast"))
            if is_last or not next_page_token:
                break
            if next_page_token in seen_tokens:
                raise AppError(
                    code="jira_pagination_stalled",
                    message="Jira issue search repeated a nextPageToken without advancing",
                    status_code=502,
                    details={"error_category": "pagination_stalled", "provider": "jira"},
                )
            seen_tokens.add(next_page_token)
            page_number += 1

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
                # Exactly one search page — never drain the generator with list().
                pages = self.iter_issue_pages(
                    project_key=probe_key,
                    lookback_days=min(_validate_lookback_days(lookback_days), 30),
                    page_size=1,
                )
                next(pages, None)
                result.issue_search_accessible = True
            except AppError as exc:
                result.issue_search_accessible = False
                category = (exc.details or {}).get("error_category") or exc.code
                result.last_error_category = category
                result.last_error_message = exc.message
                result.corrective_action = _jira_corrective(category) or (
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
        "invalid_jql": "Review project key and JQL constraints for the selected project.",
        "pagination_limit": "Catalog/search pagination exceeded the client safeguard; narrow the query.",
        "pagination_stalled": "Jira returned a repeated nextPageToken; retry or contact Atlassian support.",
    }
    return mapping.get(category or "", "Review Jira configuration and retry diagnostics.")


def _normalize_ac_field_id(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if not _CUSTOM_FIELD_RE.fullmatch(cleaned):
        raise AppError(
            code="invalid_jira_acceptance_criteria_field",
            message="Acceptance criteria field must look like customfield_NNNNN",
            status_code=400,
            details={"error_category": "invalid_configuration"},
        )
    return cleaned.lower()


def _validate_project_key(project_key: str) -> str:
    key = (project_key or "").strip().upper()
    if not key or not _PROJECT_KEY_RE.fullmatch(key):
        raise AppError(
            code="invalid_jira_project_key",
            message="Jira project key must match [A-Z][A-Z0-9_]+",
            status_code=400,
            details={"error_category": "invalid_input"},
        )
    return key


def _validate_lookback_days(lookback_days: int) -> int:
    try:
        days = int(lookback_days)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="invalid_jira_lookback_days",
            message="lookback_days must be an integer",
            status_code=400,
            details={"error_category": "invalid_input"},
        ) from exc
    if days < _MIN_LOOKBACK_DAYS or days > _MAX_LOOKBACK_DAYS:
        raise AppError(
            code="invalid_jira_lookback_days",
            message=f"lookback_days must be between {_MIN_LOOKBACK_DAYS} and {_MAX_LOOKBACK_DAYS}",
            status_code=400,
            details={"error_category": "invalid_input"},
        )
    return days


def _validate_page_size(page_size: int) -> int:
    try:
        size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise AppError(
            code="invalid_jira_page_size",
            message="page_size must be an integer",
            status_code=400,
            details={"error_category": "invalid_input"},
        ) from exc
    if size < _MIN_PAGE_SIZE or size > _MAX_PAGE_SIZE:
        raise AppError(
            code="invalid_jira_page_size",
            message=f"page_size must be between {_MIN_PAGE_SIZE} and {_MAX_PAGE_SIZE}",
            status_code=400,
            details={"error_category": "invalid_input"},
        )
    return size


def _as_nonempty_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        return text if text and text != "None" else None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() == "none":
            return None
        return cleaned
    return None


def _safe_nonneg_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_changelog(changelog: Any) -> tuple[list[dict[str, Any]], bool]:
    """Return (events, partial). Expanded changelogs are treated as potentially partial."""
    if not isinstance(changelog, dict):
        return [], True
    histories = changelog.get("histories")
    if histories is None:
        return [], True
    if not isinstance(histories, list):
        return [], True
    events: list[dict[str, Any]] = []
    for history in histories[:20]:
        if not isinstance(history, dict):
            continue
        items = history.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            events.append(
                {
                    "field": sanitize_remote_text(item.get("field")),
                    "from": sanitize_remote_text(item.get("fromString")),
                    "to": sanitize_remote_text(item.get("toString")),
                }
            )
    # Jira changelog expands are capped; never claim completeness.
    return events, True


def _detect_reopened(events: list[dict[str, Any]], *, changelog_partial: bool) -> bool | None:
    for event in events:
        field = (event.get("field") or "").lower()
        to_status = (event.get("to") or "").strip().lower()
        from_status = (event.get("from") or "").strip().lower()
        if field != "status":
            continue
        if to_status == "reopened":
            return True
        if from_status in {"done", "resolved", "closed", "complete", "completed"} and to_status not in {
            "done",
            "resolved",
            "closed",
            "complete",
            "completed",
        }:
            return True
    # Partial changelog: absence of evidence is not proof of never-reopened.
    if changelog_partial:
        return None
    return False


def _plain_field_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return sanitize_remote_text(adf_to_plain_text(value))
    return sanitize_remote_text(value)


def _parse_issue(
    item: Any, *, acceptance_criteria_field_id: str | None
) -> JiraIssue | None:
    if not isinstance(item, dict):
        return None
    key = _as_nonempty_str(item.get("key"))
    fields_obj = item.get("fields")
    if not key or not isinstance(fields_obj, dict):
        return None
    created = _parse_dt(fields_obj.get("created"))
    if created is None:
        # Do not invent a timestamp; skip malformed records.
        return None
    resolved = _parse_dt(fields_obj.get("resolutiondate"))
    issue_type_obj = fields_obj.get("issuetype")
    status_obj = fields_obj.get("status")
    issue_type = "Unknown"
    if isinstance(issue_type_obj, dict):
        issue_type = sanitize_remote_text(issue_type_obj.get("name", "Unknown")) or "Unknown"
    status = "Unknown"
    if isinstance(status_obj, dict):
        status = sanitize_remote_text(status_obj.get("name", "Unknown")) or "Unknown"

    description = _plain_field_text(fields_obj.get("description")) or None
    acceptance_criteria = None
    if acceptance_criteria_field_id:
        acceptance_criteria = _plain_field_text(fields_obj.get(acceptance_criteria_field_id)) or None

    events, changelog_partial = _extract_changelog(item.get("changelog"))
    reopened = _detect_reopened(events, changelog_partial=changelog_partial)
    return JiraIssue(
        key=sanitize_remote_text(key),
        issue_type=issue_type,
        status=status,
        created=created,
        resolved=resolved,
        summary=sanitize_remote_text(fields_obj.get("summary")),
        description=description,
        acceptance_criteria=acceptance_criteria,
        reopened=reopened,
        changelog=events,
        changelog_partial=changelog_partial,
    )


def quote_project_key(project_key: str) -> str:
    return quote(project_key, safe="")
