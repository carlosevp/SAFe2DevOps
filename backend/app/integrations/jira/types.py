from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class JiraProject:
    key: str
    name: str
    id: str


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
    acceptance_criteria: str | None = None
    reopened: bool = False
    changelog: list[dict[str, Any]] = field(default_factory=list)


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
