from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class AdoProject:
    id: str
    name: str


@dataclass(slots=True)
class AdoRepository:
    id: str
    name: str
    project_id: str
    default_branch: str


@dataclass(slots=True)
class AdoPipeline:
    id: str
    name: str
    project_id: str


@dataclass(slots=True)
class AdoCommit:
    commit_id: str
    author: str
    date: datetime
    comment: str
    to_default_branch: bool = False


@dataclass(slots=True)
class AdoPullRequest:
    id: int
    title: str
    status: str  # completed | abandoned | active
    created: datetime
    closed: datetime | None
    reviewers: list[str] = field(default_factory=list)
    jira_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AdoPipelineRun:
    id: int
    pipeline_name: str
    result: str  # succeeded | failed | canceled
    started: datetime
    finished: datetime | None
    duration_seconds: float | None = None
    is_deployment: bool = False


@dataclass(slots=True)
class AdoCapabilityResult:
    configured: bool = False
    credentials_decryptable: bool = False
    organization_accessible: bool = False
    project_catalog_accessible: bool = False
    repository_catalog_accessible: bool = False
    pipeline_catalog_accessible: bool = False
    visible_project_count: int = 0
    resolved_api_host: str | None = None
    organization: str | None = None
    last_error_category: str | None = None
    last_error_message: str | None = None
    corrective_action: str | None = None


@dataclass(slots=True)
class AdoNormalizedEvidence:
    commits_in_period: int
    active_commit_days: int
    completed_pr_count: int
    abandoned_pr_count: int
    median_pr_completion_days: float | None
    review_participation_avg: float | None
    direct_commits_to_default_branch: int
    jira_key_linkage_rate: float | None
    pipeline_run_frequency: int
    pipeline_success_rate: float | None
    failed_run_frequency: int
    median_build_duration_seconds: float | None
    time_to_next_success_after_failure_hours: float | None
    deployment_activity: int
    limitations: list[dict[str, str]]
    quality: str
    metrics: list[dict[str, Any]]
