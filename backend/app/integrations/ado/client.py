from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

from app.core.errors import AppError
from app.integrations.ado.types import (
    AdoCapabilityResult,
    AdoCommit,
    AdoPipeline,
    AdoPipelineRun,
    AdoProject,
    AdoPullRequest,
    AdoRepository,
)
from app.integrations.http import (
    normalize_ado_org_url,
    request_json,
    sanitize_host,
    sanitize_remote_text,
    with_client,
)

_JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class AdoProvider(Protocol):
    def test_connection(self) -> dict[str, Any]: ...
    def list_projects(self) -> list[AdoProject]: ...
    def list_repositories(self, project_id: str) -> list[AdoRepository]: ...
    def list_branches(self, project_id: str, repository_id: str) -> list[str]: ...
    def get_default_branch(self, project_id: str, repository_id: str) -> str: ...
    def list_pipelines(
        self, project_id: str, repository_name: str | None = None
    ) -> list[AdoPipeline]: ...
    def list_commits(
        self, *, project_id: str, repository_id: str, lookback_days: int, default_branch: str
    ) -> list[AdoCommit]: ...
    def list_pull_requests(
        self, *, project_id: str, repository_id: str, lookback_days: int
    ) -> list[AdoPullRequest]: ...
    def list_pipeline_runs(
        self, *, project_id: str, pipeline_names: list[str], lookback_days: int
    ) -> list[AdoPipelineRun]: ...
    def run_capability_checks(
        self, *, project_id: str | None = None, repository_id: str | None = None
    ) -> AdoCapabilityResult: ...


class LiveAdoProvider:
    """Reusable Azure DevOps Services REST client (PAT, api-version 7.1)."""

    def __init__(
        self,
        *,
        org_url: str,
        pat: str,
        integration_config_id: str | None = None,
    ) -> None:
        self.org_url = normalize_ado_org_url(org_url)
        self.pat = pat
        self.integration_config_id = integration_config_id
        if not self.pat:
            raise AppError(
                code="ado_not_configured",
                message="Azure DevOps PAT is required",
                status_code=400,
                details={"error_category": "invalid_configuration"},
            )
        self.organization = self.org_url.rsplit("/", 1)[-1]

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def _enc(self, value: str) -> str:
        return quote(str(value), safe="")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
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
                provider="azure_devops",
                operation=operation,
                endpoint_template=endpoint_template or path,
                integration_config_id=self.integration_config_id,
                page_number=page_number,
            )

        return with_client(self.org_url, self._headers(), _call)

    def _paged_values(
        self,
        path: str,
        *,
        operation: str,
        endpoint_template: str,
        extra_params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        continuation: str | None = None
        page_number = 1
        while True:
            params: dict[str, Any] = {"api-version": "7.1", "$top": 100}
            if extra_params:
                params.update(extra_params)
            if continuation:
                params["continuationToken"] = continuation
            data = self._request(
                "GET",
                path,
                params=params,
                operation=operation,
                page_number=page_number,
                endpoint_template=endpoint_template,
            )
            batch = (data or {}).get("value") or []
            values.extend(batch)
            # httpx exposes response headers only inside request_json; ADO often returns
            # continuationToken in the body for some APIs and x-ms-continuationtoken header
            # for others. Support body token when present; stop when empty page.
            continuation = (data or {}).get("continuationToken")
            if not continuation or not batch:
                break
            page_number += 1
            if page_number > 100:
                break
        return values

    def test_connection(self) -> dict[str, Any]:
        projects = self.list_projects()
        return {
            "ok": True,
            "organization": self.organization,
            "project_count": len(projects),
            "resolved_api_host": sanitize_host(self.org_url),
            "org_url": self.org_url,
        }

    def list_projects(self) -> list[AdoProject]:
        # Prefer stateFilter=wellFormed and paginate via $skip when continuation absent.
        projects: list[AdoProject] = []
        skip = 0
        page_number = 1
        while True:
            data = self._request(
                "GET",
                "/_apis/projects",
                params={
                    "api-version": "7.1",
                    "$top": 100,
                    "$skip": skip,
                    "stateFilter": "wellFormed",
                },
                operation="project_catalog",
                page_number=page_number,
                endpoint_template="/_apis/projects",
            )
            batch = (data or {}).get("value") or []
            for item in batch:
                projects.append(
                    AdoProject(id=str(item.get("id")), name=sanitize_remote_text(item.get("name")))
                )
            count = int((data or {}).get("count") or len(batch))
            skip += len(batch)
            if not batch or len(batch) < 100:
                break
            if count and skip >= count and count == len(batch) and page_number == 1:
                # Some responses only include the page count; continue until short page.
                pass
            page_number += 1
            if page_number > 100:
                break
        # Deduplicate by id
        by_id = {p.id: p for p in projects}
        return sorted(by_id.values(), key=lambda p: p.name.lower())

    def list_repositories(self, project_id: str) -> list[AdoRepository]:
        data = self._request(
            "GET",
            f"/{self._enc(project_id)}/_apis/git/repositories",
            params={"api-version": "7.1"},
            operation="repository_catalog",
            endpoint_template="/{project}/_apis/git/repositories",
        )
        repos: list[AdoRepository] = []
        for item in (data or {}).get("value") or []:
            default_branch = str(item.get("defaultBranch") or "refs/heads/main").replace(
                "refs/heads/", ""
            )
            repos.append(
                AdoRepository(
                    id=str(item.get("id")),
                    name=sanitize_remote_text(item.get("name")),
                    project_id=project_id,
                    default_branch=default_branch,
                )
            )
        return sorted(repos, key=lambda r: r.name.lower())

    def list_branches(self, project_id: str, repository_id: str) -> list[str]:
        data = self._request(
            "GET",
            f"/{self._enc(project_id)}/_apis/git/repositories/{self._enc(repository_id)}/refs",
            params={"filter": "heads/", "api-version": "7.1"},
            operation="list_branches",
            endpoint_template="/{project}/_apis/git/repositories/{repo}/refs",
        )
        return [
            sanitize_remote_text(str(item.get("name", "")).replace("refs/heads/", ""))
            for item in (data or {}).get("value") or []
        ]

    def get_default_branch(self, project_id: str, repository_id: str) -> str:
        repos = {r.id: r for r in self.list_repositories(project_id)}
        return repos.get(repository_id).default_branch if repository_id in repos else "main"

    def list_pipelines(
        self, project_id: str, repository_name: str | None = None
    ) -> list[AdoPipeline]:
        data = self._request(
            "GET",
            f"/{self._enc(project_id)}/_apis/pipelines",
            params={"api-version": "7.1"},
            operation="pipeline_catalog",
            endpoint_template="/{project}/_apis/pipelines",
        )
        pipelines = [
            AdoPipeline(
                id=str(item.get("id")),
                name=sanitize_remote_text(item.get("name")),
                project_id=project_id,
            )
            for item in (data or {}).get("value") or []
        ]
        if repository_name:
            lowered = repository_name.lower()
            filtered = [p for p in pipelines if lowered in p.name.lower()]
            return filtered or pipelines
        return pipelines

    def list_commits(
        self, *, project_id: str, repository_id: str, lookback_days: int, default_branch: str
    ) -> list[AdoCommit]:
        since = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
        data = self._request(
            "GET",
            f"/{self._enc(project_id)}/_apis/git/repositories/{self._enc(repository_id)}/commits",
            params={
                "searchCriteria.fromDate": since,
                "searchCriteria.itemVersion.version": default_branch,
                "api-version": "7.1",
                "$top": 500,
            },
            operation="list_commits",
            endpoint_template="/{project}/_apis/git/repositories/{repo}/commits",
        )
        commits: list[AdoCommit] = []
        for item in (data or {}).get("value") or []:
            author = (
                (item.get("author") or {}).get("email")
                or (item.get("author") or {}).get("name")
                or "unknown"
            )
            commits.append(
                AdoCommit(
                    commit_id=str(item.get("commitId")),
                    author=sanitize_remote_text(author),
                    date=_parse_dt(item.get("author", {}).get("date")) or datetime.now(UTC),
                    comment=sanitize_remote_text(item.get("comment")),
                    to_default_branch=False,
                )
            )
        return commits

    def list_pull_requests(
        self, *, project_id: str, repository_id: str, lookback_days: int
    ) -> list[AdoPullRequest]:
        data = self._request(
            "GET",
            f"/{self._enc(project_id)}/_apis/git/repositories/{self._enc(repository_id)}/pullrequests",
            params={"searchCriteria.status": "all", "api-version": "7.1", "$top": 200},
            operation="list_pull_requests",
            endpoint_template="/{project}/_apis/git/repositories/{repo}/pullrequests",
        )
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        prs: list[AdoPullRequest] = []
        for item in (data or {}).get("value") or []:
            created = _parse_dt(item.get("creationDate")) or datetime.now(UTC)
            if created < cutoff:
                continue
            title = sanitize_remote_text(item.get("title"))
            reviewers = [
                sanitize_remote_text((r.get("displayName") or r.get("uniqueName") or "reviewer"))
                for r in item.get("reviewers") or []
            ]
            status = str(item.get("status") or "active").lower()
            prs.append(
                AdoPullRequest(
                    id=int(item.get("pullRequestId") or 0),
                    title=title,
                    status="completed"
                    if status == "completed"
                    else ("abandoned" if status == "abandoned" else "active"),
                    created=created,
                    closed=_parse_dt(item.get("closedDate")),
                    reviewers=reviewers,
                    jira_keys=_JIRA_KEY.findall(title),
                )
            )
        return prs

    def list_pipeline_runs(
        self, *, project_id: str, pipeline_names: list[str], lookback_days: int
    ) -> list[AdoPipelineRun]:
        pipelines = {p.name: p for p in self.list_pipelines(project_id)}
        runs: list[AdoPipelineRun] = []
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        for name in pipeline_names:
            pipeline = pipelines.get(name)
            if pipeline is None:
                continue
            data = self._request(
                "GET",
                f"/{self._enc(project_id)}/_apis/pipelines/{self._enc(pipeline.id)}/runs",
                params={"api-version": "7.1", "$top": 100},
                operation="list_pipeline_runs",
                endpoint_template="/{project}/_apis/pipelines/{pipelineId}/runs",
            )
            for item in (data or {}).get("value") or []:
                started = _parse_dt(item.get("createdDate")) or datetime.now(UTC)
                if started < cutoff:
                    continue
                finished = _parse_dt(item.get("finishedDate"))
                result = str(item.get("result") or item.get("state") or "unknown").lower()
                runs.append(
                    AdoPipelineRun(
                        id=int(item.get("id") or 0),
                        pipeline_name=name,
                        result="succeeded"
                        if "succeed" in result
                        else ("failed" if "fail" in result else result),
                        started=started,
                        finished=finished,
                        duration_seconds=(finished - started).total_seconds() if finished else None,
                        is_deployment="cd" in name.lower() or "deploy" in name.lower(),
                    )
                )
        return runs

    def run_capability_checks(
        self, *, project_id: str | None = None, repository_id: str | None = None
    ) -> AdoCapabilityResult:
        result = AdoCapabilityResult(
            configured=True,
            credentials_decryptable=True,
            resolved_api_host=sanitize_host(self.org_url),
            organization=self.organization,
        )
        try:
            projects = self.list_projects()
            result.organization_accessible = True
            result.project_catalog_accessible = True
            result.visible_project_count = len(projects)
            if not projects:
                result.last_error_category = "no_visible_projects"
                result.last_error_message = (
                    "Azure DevOps accepted the PAT, but no projects are visible. "
                    "Verify Project and Team (Read) scope and project membership."
                )
                result.corrective_action = (
                    "Grant Project and Team (Read) and ensure the identity can see pilot projects."
                )
                return result
        except AppError as exc:
            category = (exc.details or {}).get("error_category") or exc.code
            result.last_error_category = category
            result.last_error_message = exc.message
            if category == "authentication_failed":
                result.corrective_action = "PAT appears expired or revoked; create a new PAT."
            else:
                result.corrective_action = _ado_corrective(category)
            return result

        probe_project = project_id or projects[0].id
        try:
            repos = self.list_repositories(probe_project)
            result.repository_catalog_accessible = True
            if repository_id and repository_id not in {r.id for r in repos} and repos:
                repository_id = repos[0].id
            elif not repository_id and repos:
                repository_id = repos[0].id
        except AppError as exc:
            category = (exc.details or {}).get("error_category") or exc.code
            result.repository_catalog_accessible = False
            result.last_error_category = (
                "missing_code_scope" if category == "permission_denied" else category
            )
            result.last_error_message = exc.message
            result.corrective_action = (
                "Project is visible but Code (Read) appears missing for repositories."
            )
            return result

        try:
            self.list_pipelines(probe_project)
            result.pipeline_catalog_accessible = True
        except AppError as exc:
            category = (exc.details or {}).get("error_category") or exc.code
            result.pipeline_catalog_accessible = False
            result.last_error_category = (
                "missing_build_scope" if category == "permission_denied" else category
            )
            result.last_error_message = exc.message
            result.corrective_action = (
                "Repository access works but Build (Read) appears missing for pipelines."
            )
        return result


def _ado_corrective(category: str | None) -> str:
    mapping = {
        "authentication_failed": "Create a new PAT; the previous token may be expired or revoked.",
        "permission_denied": "Add missing PAT scopes: Project/Team Read, Code Read, Build Read.",
        "missing_code_scope": "Add Code (Read) to the PAT.",
        "missing_build_scope": "Add Build (Read) to the PAT.",
        "throttled": "Azure DevOps is throttling requests; retry shortly.",
        "network_timeout": "Outbound HTTPS to Azure DevOps timed out; check proxy/DNS/firewall.",
        "network_or_tls_failure": "TLS/network failure; verify corporate CA and proxy settings.",
        "invalid_url": "Set organization to https://dev.azure.com/{organization}.",
        "no_visible_projects": "Grant project visibility / Project and Team (Read).",
    }
    return mapping.get(category or "", "Review Azure DevOps organization URL and PAT scopes.")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
