from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


ClaimKind = Literal[
    "observed_evidence",
    "assessment_interpretation",
    "illustrative_example",
    "recommendation",
]

RefType = Literal[
    "interview_turn",
    "evidence_metric",
    "practice_coverage",
    "enterprise_finding",
    "admin_observation",
]


class SourceRef(StrictSchema):
    ref_type: RefType
    ref_key: str
    label: str | None = None


class LabeledClaim(StrictSchema):
    kind: ClaimKind
    text: str = Field(min_length=1, max_length=4000)
    source_refs: list[SourceRef] = Field(default_factory=list)


class MethodologySection(StrictSchema):
    team_product: str
    evidence_period_days: int
    jira_project: str | None = None
    ado_repository: str | None = None
    ado_pipelines: list[str] = Field(default_factory=list)
    participation_approach: str
    evidence_influence_mode: str
    framework_version: str
    enterprise_standard_version: str | None = None
    limitations: list[str] = Field(default_factory=list)


class ExecutiveNarrative(StrictSchema):
    delivery_model: str
    strongest_capabilities: list[str] = Field(default_factory=list)
    recurring_constraints: list[str] = Field(default_factory=list)
    cross_domain_themes: list[str] = Field(default_factory=list)
    next_maturity_transition: str
    confidence: str
    narrative: str = Field(min_length=1, max_length=12000)


class DomainReview(StrictSchema):
    domain_key: str
    domain_name: str
    current_state_narrative: str
    human_evidence: list[LabeledClaim] = Field(default_factory=list)
    tool_evidence: list[LabeledClaim] = Field(default_factory=list)
    strengths: list[LabeledClaim] = Field(default_factory=list)
    gaps: list[LabeledClaim] = Field(default_factory=list)
    why_gaps_matter: list[LabeledClaim] = Field(default_factory=list)
    illustrative_examples: list[LabeledClaim] = Field(default_factory=list)
    progression_path: list[LabeledClaim] = Field(default_factory=list)
    related_enterprise_standards: list[str] = Field(default_factory=list)
    confidence: str
    limitations: list[str] = Field(default_factory=list)


class PracticeReview(StrictSchema):
    practice_key: str
    practice_name: str
    domain_key: str
    maturity_level: str | None = None
    final_score: float | None = None
    interpretation: str
    evidence_observed: list[LabeledClaim] = Field(default_factory=list)
    strengths: list[LabeledClaim] = Field(default_factory=list)
    gaps: list[LabeledClaim] = Field(default_factory=list)
    better_could_look_like: list[LabeledClaim] = Field(default_factory=list)
    practical_examples: list[LabeledClaim] = Field(default_factory=list)
    recommendation: LabeledClaim | None = None
    related_action_titles: list[str] = Field(default_factory=list)
    confidence: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class CrossCuttingTheme(StrictSchema):
    theme_key: str
    title: str
    narrative: str
    claims: list[LabeledClaim] = Field(default_factory=list)


class EnterpriseStandardsReview(StrictSchema):
    aligned: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    insufficient_evidence: list[str] = Field(default_factory=list)
    relationship_to_safe: str
    recommendations: list[LabeledClaim] = Field(default_factory=list)


class RoadmapContextItem(StrictSchema):
    action_title: str
    observed_problem: str
    why_selected: str
    expected_benefit: str
    implementation_example: LabeledClaim
    owner_type: str
    dependencies: list[str] = Field(default_factory=list)
    kpi_signal: str
    related_practice_keys: list[str] = Field(default_factory=list)
    related_standard_keys: list[str] = Field(default_factory=list)
    time_horizon: str


class EvidenceLimitationsAppendix(StrictSchema):
    evidence_sources: list[str] = Field(default_factory=list)
    metrics_used: list[str] = Field(default_factory=list)
    missing_or_unreliable: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    interview_primary_areas: list[str] = Field(default_factory=list)
    tool_primary_areas: list[str] = Field(default_factory=list)
    excluded_data: list[str] = Field(default_factory=list)
    confidence_explanation: str


class GenerationMetadata(StrictSchema):
    model_name: str
    generated_at: str
    section_statuses: dict[str, str] = Field(default_factory=dict)
    incomplete: bool = False
    warnings: list[str] = Field(default_factory=list)
    schema_version: int = 1


class DetailedAssessmentReport(StrictSchema):
    schema_version: int = 1
    methodology: MethodologySection
    executive_narrative: ExecutiveNarrative
    domain_reviews: list[DomainReview] = Field(default_factory=list)
    practice_reviews: list[PracticeReview] = Field(default_factory=list)
    cross_cutting_themes: list[CrossCuttingTheme] = Field(default_factory=list)
    enterprise_standards_review: EnterpriseStandardsReview
    roadmap_context: list[RoadmapContextItem] = Field(default_factory=list)
    evidence_limitations: EvidenceLimitationsAppendix
    generation_metadata: GenerationMetadata


class DetailedReportSectionEditIn(StrictSchema):
    section: str
    content: dict[str, Any]


class DetailedReportGenerateIn(StrictSchema):
    section: str | None = None  # None = full report
