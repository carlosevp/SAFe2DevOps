from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import (
    AssessmentStatus,
    CoverageState,
    EvidenceInfluenceMode,
    ParticipationMode,
)


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AssessmentCreate(StrictSchema):
    team_name: str = Field(min_length=1, max_length=200)
    product_service_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    value_stream: str | None = None
    owner_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    lookback_days: int = Field(default=90, ge=30, le=365)
    evidence_influence_mode: EvidenceInfluenceMode = EvidenceInfluenceMode.BALANCED
    participation_mode: ParticipationMode = ParticipationMode.HYBRID_REMOTE


class AssessmentSourceSelectionIn(StrictSchema):
    """Jira/ADO selections. Empty project/repo fields mean interview-only (skip that system)."""

    jira_project_key: str = ""
    jira_project_name: str | None = None
    jira_board_id: str | None = None
    jira_board_name: str | None = None
    jira_jql: str | None = None
    ado_project_id: str = ""
    ado_project_name: str | None = None
    ado_repository_id: str = ""
    ado_repository_name: str = ""
    default_branch: str = "main"
    selected_pipelines: list[dict[str, Any]] = Field(default_factory=list)


class AssessmentSummary(StrictSchema):
    id: str
    team_name: str
    product_service_name: str
    owner_name: str
    owner_email: str
    lookback_days: int
    evidence_influence_mode: EvidenceInfluenceMode
    participation_mode: ParticipationMode
    status: AssessmentStatus
    created_at: datetime
    updated_at: datetime


class PracticeCoverageParticipant(StrictSchema):
    """Participant-safe coverage view — never includes AI candidate scores."""

    practice_key: str
    domain_key: str
    coverage_state: CoverageState
    open_gaps: list[str] = Field(default_factory=list)
    confidence: float | None = None

    @field_validator("open_gaps", mode="before")
    @classmethod
    def _parse_gaps(cls, value: object) -> object:
        if isinstance(value, str):
            import json

            return json.loads(value or "[]")
        return value


class PracticeCoverageAdmin(PracticeCoverageParticipant):
    evidence_summaries: list[str] = Field(default_factory=list)
    source_turn_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    ai_candidate_score: float | None = None
    admin_final_score: float | None = None
    admin_rationale: str | None = None


class AdminScoreUpdate(StrictSchema):
    score: float = Field(ge=1.0, le=5.0)
    rationale: str | None = None


class LifecycleTransitionRequest(StrictSchema):
    status: AssessmentStatus


class PublishedReportOut(StrictSchema):
    id: str
    assessment_id: str
    version: int
    title: str
    summary_markdown: str
    scores: dict[str, float]
    published_by: str
    published_at: datetime
    immutable: Literal[True] = True


class AssessmentModelPublic(StrictSchema):
    version: str
    domains: list[dict[str, Any]]
    evidence_influence_policies: list[str]
    maturity_levels: list[dict[str, Any]]


class EvidenceMetricOut(StrictSchema):
    key: str
    label: str
    value_text: str
    value_numeric: float | None = None
    source_system: str
    trend: str | None = None
    freshness_label: str | None = None


class EvidenceLimitationOut(StrictSchema):
    code: str
    message: str
    source_system: str | None = None


class EvidenceSnapshotOut(StrictSchema):
    id: str
    assessment_id: str
    lookback_days: int
    collected_at: datetime
    jira_project_key: str
    ado_repository_name: str
    provenance_summary: str
    payload_ref: str | None = None
    payload_checksum: str | None = None
    quality: str
    immutable: bool
    is_representative: bool
    metrics: list[EvidenceMetricOut] = Field(default_factory=list)
    limitations: list[EvidenceLimitationOut] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class EvidenceExclusionsIn(StrictSchema):
    exclusions: list[str] = Field(default_factory=list)
