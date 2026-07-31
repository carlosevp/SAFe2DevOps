from __future__ import annotations

import base64
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.integrations.ado.types import (
    AdoCommit,
    AdoPipeline,
    AdoPipelineRun,
    AdoProject,
    AdoPullRequest,
    AdoRepository,
)
from app.integrations.http import request_json, sanitize_remote_text, validate_https_url, with_client

_JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class AdoProvider(Protocol):
    def test_connection(self) -> dict[str, Any]: ...
    def list_projects(self) -> list[AdoProject]: ...
    def list_repositories(self, project_id: str) -> list[AdoRepository]: ...
    def list_branches(self, project_id: str, repository_id: str) -> list[str]: ...
    def get_default_branch(self, project_id: str, repository_id: str) -> str: ...
    def list_pipelines(self, project_id: str, repository_name: str | None = None) -> list[AdoPipeline]: ...
    def list_commits(self, *, project_id: str, repository_id: str, lookback_days: int, default_branch: str) -> list[AdoCommit]: ...
    def list_pull_requests(self, *, project_id: str, repository_id: str, lookback_days: int) -> list[AdoPullRequest]: ...
    def list_pipeline_runs(self, *, project_id: str, pipeline_names: list[str], lookback_days: int) -> list[AdoPipelineRun]: ...


class LiveAdoProvider:
    def __init__(self, *, org_url: str, pat: str) -> None:
        self.org_url = validate_https_url(org_url, label="Azure DevOps organization URL")
        self.pat = pat

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json"}

    def test_connection(self) -> dict[str, Any]:
        def _call(client):
            data = request_json(client, "GET", "/_apis/projects", params={"api-version": "7.1"})
            count = len((data or {}).get("value") or [])
            return {"ok": True, "organization": self.org_url.rsplit("/", 1)[-1], "project_count": count}

        return with_client(self.org_url, self._headers(), _call)

    def list_projects(self) -> list[AdoProject]:
        def _call(client):
            data = request_json(client, "GET", "/_apis/projects", params={"api-version": "7.1"})
            return [
                AdoProject(id=str(item.get("id")), name=sanitize_remote_text(item.get("name")))
                for item in (data or {}).get("value") or []
            ]

        return with_client(self.org_url, self._headers(), _call)

    def list_repositories(self, project_id: str) -> list[AdoRepository]:
        def _call(client):
            data = request_json(
                client,
                "GET",
                f"/{project_id}/_apis/git/repositories",
                params={"api-version": "7.1"},
            )
            repos: list[AdoRepository] = []
            for item in (data or {}).get("value") or []:
                default_branch = str(item.get("defaultBranch") or "refs/heads/main").replace("refs/heads/", "")
                repos.append(
                    AdoRepository(
                        id=str(item.get("id")),
                        name=sanitize_remote_text(item.get("name")),
                        project_id=project_id,
                        default_branch=default_branch,
                    )
                )
            return repos

        return with_client(self.org_url, self._headers(), _call)

    def list_branches(self, project_id: str, repository_id: str) -> list[str]:
        def _call(client):
            data = request_json(
                client,
                "GET",
                f"/{project_id}/_apis/git/repositories/{repository_id}/refs",
                params={"filter": "heads/", "api-version": "7.1"},
            )
            return [
                sanitize_remote_text(str(item.get("name", "")).replace("refs/heads/", ""))
                for item in (data or {}).get("value") or []
            ]

        return with_client(self.org_url, self._headers(), _call)

    def get_default_branch(self, project_id: str, repository_id: str) -> str:
        repos = {r.id: r for r in self.list_repositories(project_id)}
        return repos.get(repository_id).default_branch if repository_id in repos else "main"

    def list_pipelines(self, project_id: str, repository_name: str | None = None) -> list[AdoPipeline]:
        def _call(client):
            data = request_json(
                client,
                "GET",
                f"/{project_id}/_apis/pipelines",
                params={"api-version": "7.1"},
            )
            pipelines = [
                AdoPipeline(id=str(item.get("id")), name=sanitize_remote_text(item.get("name")), project_id=project_id)
                for item in (data or {}).get("value") or []
            ]
            if repository_name:
                lowered = repository_name.lower()
                filtered = [p for p in pipelines if lowered in p.name.lower()]
                return filtered or pipelines
            return pipelines

        return with_client(self.org_url, self._headers(), _call)

    def list_commits(self, *, project_id: str, repository_id: str, lookback_days: int, default_branch: str) -> list[AdoCommit]:
        since = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

        def _call(client):
            data = request_json(
                client,
                "GET",
                f"/{project_id}/_apis/git/repositories/{repository_id}/commits",
                params={"searchCriteria.fromDate": since, "api-version": "7.1", "$top": 500},
            )
            commits: list[AdoCommit] = []
            for item in (data or {}).get("value") or []:
                author = (item.get("author") or {}).get("email") or (item.get("author") or {}).get("name") or "unknown"
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

        return with_client(self.org_url, self._headers(), _call)

    def list_pull_requests(self, *, project_id: str, repository_id: str, lookback_days: int) -> list[AdoPullRequest]:
        def _call(client):
            data = request_json(
                client,
                "GET",
                f"/{project_id}/_apis/git/repositories/{repository_id}/pullrequests",
                params={"searchCriteria.status": "all", "api-version": "7.1", "$top": 200},
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
                        status="completed" if status == "completed" else ("abandoned" if status == "abandoned" else "active"),
                        created=created,
                        closed=_parse_dt(item.get("closedDate")),
                        reviewers=reviewers,
                        jira_keys=_JIRA_KEY.findall(title),
                    )
                )
            return prs

        return with_client(self.org_url, self._headers(), _call)

    def list_pipeline_runs(self, *, project_id: str, pipeline_names: list[str], lookback_days: int) -> list[AdoPipelineRun]:
        pipelines = {p.name: p for p in self.list_pipelines(project_id)}
        runs: list[AdoPipelineRun] = []
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        for name in pipeline_names:
            pipeline = pipelines.get(name)
            if pipeline is None:
                continue

            def _call(client, pipeline_id=pipeline.id, pipeline_name=name):
                data = request_json(
                    client,
                    "GET",
                    f"/{project_id}/_apis/pipelines/{pipeline_id}/runs",
                    params={"api-version": "7.1", "$top": 100},
                )
                local: list[AdoPipelineRun] = []
                for item in (data or {}).get("value") or []:
                    started = _parse_dt(item.get("createdDate")) or datetime.now(UTC)
                    if started < cutoff:
                        continue
                    finished = _parse_dt(item.get("finishedDate"))
                    result = str(item.get("result") or item.get("state") or "unknown").lower()
                    local.append(
                        AdoPipelineRun(
                            id=int(item.get("id") or 0),
                            pipeline_name=pipeline_name,
                            result="succeeded" if "succeed" in result else ("failed" if "fail" in result else result),
                            started=started,
                            finished=finished,
                            duration_seconds=(finished - started).total_seconds() if finished else None,
                            is_deployment="cd" in pipeline_name.lower() or "deploy" in pipeline_name.lower(),
                        )
                    )
                return local

            runs.extend(with_client(self.org_url, self._headers(), _call))
        return runs


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
