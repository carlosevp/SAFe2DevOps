from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    APPLICABILITY_FIELDS,
    ApplicabilityMode,
    ConditionLogicalGroup,
    ConditionOperator,
    RequirementLevel,
    StandardFindingStatus,
)


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StandardConditionIn(StrictSchema):
    field: str
    operator: ConditionOperator = ConditionOperator.EQUALS
    value: str = ""
    logical_group: ConditionLogicalGroup = ConditionLogicalGroup.ALL

    @field_validator("field")
    @classmethod
    def _field_allowed(cls, value: str) -> str:
        if value not in APPLICABILITY_FIELDS:
            raise ValueError(f"Unsupported applicability field: {value}")
        return value


class StandardConditionOut(StandardConditionIn):
    id: str


class EnterpriseStandardIn(StrictSchema):
    stable_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=2, max_length=240)
    category: str = Field(min_length=2, max_length=80)
    description: str = ""
    requirement_level: RequirementLevel = RequirementLevel.PREFERRED
    active: bool = True
    applicability_mode: ApplicabilityMode = ApplicabilityMode.ALWAYS
    mapped_practice_keys: list[str] = Field(default_factory=list)
    primary_interview_guidance: str = ""
    follow_up_guidance: str = ""
    evidence_expectations: str = ""
    recommendation_when_unmet: str = ""
    display_order: int = 100
    conditions: list[StandardConditionIn] = Field(default_factory=list)


class EnterpriseStandardUpdate(StrictSchema):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = None
    requirement_level: RequirementLevel | None = None
    active: bool | None = None
    applicability_mode: ApplicabilityMode | None = None
    mapped_practice_keys: list[str] | None = None
    primary_interview_guidance: str | None = None
    follow_up_guidance: str | None = None
    evidence_expectations: str | None = None
    recommendation_when_unmet: str | None = None
    display_order: int | None = None
    conditions: list[StandardConditionIn] | None = None


class EnterpriseStandardOut(StrictSchema):
    id: str
    stable_key: str
    title: str
    category: str
    description: str
    requirement_level: RequirementLevel
    active: bool
    applicability_mode: ApplicabilityMode
    mapped_practice_keys: list[str]
    primary_interview_guidance: str
    follow_up_guidance: str
    evidence_expectations: str
    recommendation_when_unmet: str
    display_order: int
    conditions: list[StandardConditionOut]
    referenced: bool = False
    created_at: datetime
    updated_at: datetime


class StandardsImportBundle(StrictSchema):
    standards: list[EnterpriseStandardIn]


class TechnologyContextIn(StrictSchema):
    primary_technology: str = ""
    application_type: str = ""
    current_platform: str = ""
    target_platform: str = ""
    hosting_location: str = ""
    customer_exposure: str = ""
    lifecycle_stage: str = ""
    application_has_secrets: bool = True
    uses_cicd: bool = True
    context_tags: list[str] = Field(default_factory=list)
    notes: str = ""


class TechnologyContextOut(TechnologyContextIn):
    id: str
    assessment_id: str
    confirmed_at: datetime | None = None
    applicable_standard_count: int = 0
    applicable_standard_keys: list[str] = Field(default_factory=list)


class StandardSnapshotOut(StrictSchema):
    id: str
    assessment_id: str
    source_standard_id: str | None
    stable_key: str
    definition: dict[str, Any]
    source_updated_at: datetime | None
    snapshot_at: datetime


class StandardFindingOut(StrictSchema):
    id: str
    assessment_id: str
    snapshot_id: str
    stable_key: str
    title: str
    category: str
    requirement_level: RequirementLevel
    mapped_practice_keys: list[str]
    status: StandardFindingStatus
    human_evidence_summary: str
    tool_evidence_summary: str
    source_interview_turn_ids: list[str]
    source_evidence_metric_ids: list[str]
    confidence: float | None
    observation: str
    recommendation: str
    admin_edited_status: bool
    admin_note: str
    time_horizon: str = "next_sprint"


class StandardFindingUpdateIn(StrictSchema):
    status: StandardFindingStatus | None = None
    observation: str | None = None
    recommendation: str | None = None
    admin_note: str | None = None


class StandardUpdateAI(StrictSchema):
    """Model-produced enterprise standard update. Keys validated server-side."""

    standard_key: str = Field(min_length=1, max_length=80)
    applicability_confirmation: bool = True
    status: StandardFindingStatus
    evidence_summary: str = Field(default="", max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)
    missing_evidence: list[str] = Field(default_factory=list)
    recommendation_candidate: str = Field(default="", max_length=4000)


class PublishedEnterpriseStandardsOut(StrictSchema):
    applicable_count: int
    aligned_count: int
    partially_aligned_count: int
    finding_count: int
    insufficient_evidence_count: int
    not_applicable_count: int
    findings_by_category: dict[str, list[dict[str, Any]]]
    recommendation_cards: list[dict[str, Any]]
