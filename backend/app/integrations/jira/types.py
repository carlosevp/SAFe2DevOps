from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

JIRA_CREDENTIAL_CLASSIC = "classic_account_api_token"
JIRA_CREDENTIAL_SCOPED = "scoped_service_account_token"
JIRA_CREDENTIAL_MODES = frozenset({JIRA_CREDENTIAL_CLASSIC, JIRA_CREDENTIAL_SCOPED})


@dataclass(slots=True)
class JiraProject:
    key: str
    name: str
    id: str
    project_type_key: str | None = None
    style: str | None = None


@dataclass(slots=True)
class JiraBoard:
    id: str
    name: str
    project_key: str


@dataclass(slots=True)
class JiraIssue:
    key: str
    issue_type: str
    status: str
    created: datetime
    resolved: datetime | None
    summary: str
    description: str | None = None
    acceptance_criteria: str | None = None
    # None means reopened status was not determined (changelog missing/partial).
    reopened: bool | None = None
    changelog: list[dict[str, Any]] = field(default_factory=list)
    changelog_partial: bool = True


@dataclass(slots=True)
class JiraNormalizedEvidence:
    completed_items: int
    issue_type_distribution: dict[str, int]
    bugs_created: int
    bugs_resolved: int
    approximate_cycle_time_days: float | None
    issue_aging_days_p50: float | None
    reopened_work: int
    approximate_wip: int
    release_version_usage: int
    acceptance_criteria_presence_rate: float | None
    limitations: list[dict[str, str]]
    quality: str
    metrics: list[dict[str, Any]]
    raw_issue_count: int


@dataclass(slots=True)
class JiraCapabilityResult:
    configured: bool = False
    credentials_decryptable: bool = False
    identity_authenticated: bool = False
    project_catalog_accessible: bool = False
    issue_search_accessible: bool | None = None
    visible_project_count: int = 0
    resolved_api_host: str | None = None
    cloud_id_present: bool = False
    credential_mode: str | None = None
    display_name: str | None = None
    last_error_category: str | None = None
    last_error_message: str | None = None
    corrective_action: str | None = None
