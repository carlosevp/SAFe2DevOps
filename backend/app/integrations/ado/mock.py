from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.integrations.ado.types import (
    AdoCapabilityResult,
    AdoCommit,
    AdoPipeline,
    AdoPipelineRun,
    AdoProject,
    AdoPullRequest,
    AdoRepository,
)
from app.integrations.http import sanitize_remote_text

_JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class MockAdoProvider:
    def __init__(self, *, org_url: str = "https://dev.azure.com/claimsco") -> None:
        self.org_url = org_url

    def test_connection(self) -> dict[str, Any]:
        return {"ok": True, "organization": "claimsco", "org_url": self.org_url}

    def list_projects(self) -> list[AdoProject]:
        return [
            AdoProject(id="p1", name="Claims Co"),
            AdoProject(id="p2", name="InfraTeam"),
            AdoProject(id="p3", name="Platform Services"),
        ]

    def list_repositories(self, project_id: str) -> list[AdoRepository]:
        if project_id != "p1":
            return [
                AdoRepository(
                    id="r-other", name="shared-tools", project_id=project_id, default_branch="main"
                )
            ]
        return [
            AdoRepository(id="r-api", name="claims-api", project_id="p1", default_branch="main"),
            AdoRepository(
                id="r-portal", name="claims-portal", project_id="p1", default_branch="main"
            ),
            AdoRepository(
                id="r-libs", name="claims-shared-libs", project_id="p1", default_branch="main"
            ),
        ]

    def list_branches(self, project_id: str, repository_id: str) -> list[str]:
        return ["main", "develop", "release/2026.07"]

    def get_default_branch(self, project_id: str, repository_id: str) -> str:
        repos = {r.id: r for r in self.list_repositories(project_id)}
        return repos.get(
            repository_id,
            AdoRepository(id=repository_id, name="x", project_id=project_id, default_branch="main"),
        ).default_branch

    def list_pipelines(
        self, project_id: str, repository_name: str | None = None
    ) -> list[AdoPipeline]:
        prefix = (
            "claims-api" if (repository_name or "claims-api").startswith("claims") else "shared"
        )
        return [
            AdoPipeline(id="pl1", name=f"{prefix}-CI", project_id=project_id),
            AdoPipeline(id="pl2", name=f"{prefix}-CD-prod", project_id=project_id),
            AdoPipeline(id="pl3", name=f"{prefix}-PR-validation", project_id=project_id),
        ]

    def list_commits(
        self, *, project_id: str, repository_id: str, lookback_days: int, default_branch: str
    ) -> list[AdoCommit]:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        commits: list[AdoCommit] = []
        for idx in range(312 if repository_id == "r-api" else 40):
            day = now - timedelta(days=idx % max(lookback_days, 1))
            if idx % 19 == 0:
                author = "dependabot@users.noreply.github.com"
                comment = "dependabot: bump dependency"
            else:
                author = "dev@claimsco.example"
                comment = f"CLAIM-{1000 + idx}: update service logic"
            commits.append(
                AdoCommit(
                    commit_id=f"c{idx:04d}",
                    author=author,
                    date=day,
                    comment=sanitize_remote_text(comment),
                    to_default_branch=idx % 11 == 0,
                )
            )
        return commits

    def list_pull_requests(
        self, *, project_id: str, repository_id: str, lookback_days: int
    ) -> list[AdoPullRequest]:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        prs: list[AdoPullRequest] = []
        completed = 44 if repository_id == "r-api" else 8
        abandoned = 5 if repository_id == "r-api" else 1
        for idx in range(completed + abandoned):
            created = now - timedelta(days=(idx % max(lookback_days, 1)))
            closed = created + timedelta(hours=20 + idx % 30)
            status = "completed" if idx < completed else "abandoned"
            title = f"CLAIM-{2000 + idx} improve delivery path"
            prs.append(
                AdoPullRequest(
                    id=idx + 1,
                    title=sanitize_remote_text(title),
                    status=status,
                    created=created,
                    closed=closed,
                    reviewers=["alice@claimsco.example", "bob@claimsco.example"][: 1 + (idx % 2)],
                    jira_keys=_JIRA_KEY.findall(title),
                )
            )
        return prs

    def list_pipeline_runs(
        self,
        *,
        project_id: str,
        pipeline_names: list[str],
        lookback_days: int,
    ) -> list[AdoPipelineRun]:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
        runs: list[AdoPipelineRun] = []
        rid = 1
        for name in pipeline_names:
            count = 61 if "CI" in name else 31 if "CD" in name else 44
            for idx in range(count):
                started = now - timedelta(hours=idx * 6)
                if started < now - timedelta(days=lookback_days):
                    continue
                failed = idx % 7 == 0
                finished = started + timedelta(minutes=8 + idx % 10)
                runs.append(
                    AdoPipelineRun(
                        id=rid,
                        pipeline_name=name,
                        result="failed" if failed else "succeeded",
                        started=started,
                        finished=finished,
                        duration_seconds=(finished - started).total_seconds(),
                        is_deployment="CD" in name,
                    )
                )
                rid += 1
        return runs

    def run_capability_checks(
        self, *, project_id: str | None = None, repository_id: str | None = None
    ) -> AdoCapabilityResult:
        projects = self.list_projects()
        return AdoCapabilityResult(
            configured=True,
            credentials_decryptable=True,
            organization_accessible=True,
            project_catalog_accessible=True,
            repository_catalog_accessible=True,
            pipeline_catalog_accessible=True,
            visible_project_count=len(projects),
            resolved_api_host="dev.azure.com",
            organization="claimsco",
        )
