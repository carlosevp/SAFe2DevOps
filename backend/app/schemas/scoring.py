from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PracticeScoreAI(StrictSchema):
    practice_key: str = Field(min_length=1, max_length=64)
    coverage_state: Literal["not_discussed", "partial", "sufficient", "clarify"]
    ai_candidate_score: float = Field(ge=1.0, le=5.0)
    named_maturity_level: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0.0, le=1.0)
    human_evidence: str = Field(default="", max_length=4000)
    jira_evidence: str = Field(default="", max_length=4000)
    ado_evidence: str = Field(default="", max_length=4000)
    source_turn_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=4000)
    missing_information: list[str] = Field(default_factory=list)
    recommendation: str = Field(default="", max_length=2000)


class ImprovementActionAI(StrictSchema):
    title: str = Field(min_length=1, max_length=240)
    observation: str = Field(min_length=1, max_length=2000)
    practice_key: str = Field(min_length=1, max_length=64)
    domain_key: str = Field(min_length=1, max_length=64)
    supporting_evidence: str = Field(min_length=1, max_length=2000)
    why_it_matters: str = Field(min_length=1, max_length=2000)
    recommended_action: str = Field(min_length=1, max_length=2000)
    time_horizon: Literal["next_sprint", "ninety_days", "longer_term"]
    kpi: str = Field(min_length=1, max_length=240)
    priority: int = Field(ge=1, le=5)


class CandidateScoringAI(StrictSchema):
    """Strict Structured Outputs schema for candidate scoring + improvement planning."""

    practice_scores: list[PracticeScoreAI] = Field(min_length=1, max_length=16)
    overall_maturity: float = Field(ge=1.0, le=5.0)
    confidence_summary: Literal["Low", "Medium", "High"]
    evidence_quality: Literal["Limited", "Adequate", "Strong"]
    strengths: list[str] = Field(default_factory=list)
    maturity_gaps: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    improvement_actions: list[ImprovementActionAI] = Field(default_factory=list)
    chart_summary: str = Field(min_length=1, max_length=2000)


class PracticeReviewOut(StrictSchema):
    practice_key: str
    practice_name: str
    domain_key: str
    domain_short_name: str
    coverage_state: str
    ai_candidate_score: float | None = None
    named_maturity_level: str | None = None
    confidence: float | None = None
    human_evidence: str = ""
    jira_evidence: str = ""
    ado_evidence: str = ""
    source_turn_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    scoring_rationale: str = ""
    missing_information: list[str] = Field(default_factory=list)
    admin_final_score: float | None = None
    admin_rationale: str | None = None
    evidence_unreliable: bool = False
    admin_observation: str | None = None
    recommendation_text: str | None = None


class ImprovementActionOut(StrictSchema):
    id: str
    title: str
    practice_key: str | None
    domain_key: str | None
    observation: str
    supporting_evidence: str
    why_it_matters: str
    recommended_action: str
    time_horizon: str
    kpi: str
    priority: int
    related_practice_keys: list[str] = Field(default_factory=list)
    related_standard_keys: list[str] = Field(default_factory=list)
    related_standard_titles: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class DomainRadarPoint(StrictSchema):
    domain_key: str
    domain_short_name: str
    domain_name: str
    score: float
    weight: float


class HeatmapCell(StrictSchema):
    practice_key: str
    practice_name: str
    domain_short_name: str
    score: float | None
    named_maturity_level: str | None = None


class ReviewPackageOut(StrictSchema):
    assessment_id: str
    team_name: str
    product_service_name: str
    status: str
    lookback_days: int
    evidence_influence_mode: str
    overall_maturity: float | None = None
    confidence_summary: str | None = None
    evidence_quality: str | None = None
    strengths: list[str] = Field(default_factory=list)
    maturity_gaps: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    practices: list[PracticeReviewOut] = Field(default_factory=list)
    improvement_actions: list[ImprovementActionOut] = Field(default_factory=list)
    radar: list[DomainRadarPoint] = Field(default_factory=list)
    heatmap: list[HeatmapCell] = Field(default_factory=list)
    chart_summary: str = ""
    prompt_config_version: str = "assessment_model.yaml"
    model_name: str | None = None
    ready_to_publish: bool = False
    # Admin-only AI vs final comparison
    ai_vs_final: list[dict] = Field(default_factory=list)


class AdminScoreActionIn(StrictSchema):
    score: float | None = Field(default=None, ge=1.0, le=5.0)
    rationale: str | None = None
    accept_candidate: bool = False


class MarkUnreliableIn(StrictSchema):
    unreliable: bool = True
    note: str | None = Field(default=None, max_length=2000)


class ObservationIn(StrictSchema):
    observation: str = Field(min_length=1, max_length=4000)


class RecommendationIn(StrictSchema):
    recommendation_text: str = Field(min_length=1, max_length=4000)


class ImprovementEditIn(StrictSchema):
    title: str | None = Field(default=None, max_length=240)
    observation: str | None = None
    supporting_evidence: str | None = None
    why_it_matters: str | None = None
    recommended_action: str | None = None
    time_horizon: Literal["next_sprint", "ninety_days", "longer_term"] | None = None
    kpi: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)


class PublishedResultsOut(StrictSchema):
    assessment_id: str
    version: int
    title: str
    team_name: str
    product_service_name: str
    published_at: datetime
    lookback_days: int
    evidence_influence_mode: str
    overall_maturity: float
    confidence_summary: str
    evidence_quality: str
    practices_assessed: int
    practices_total: int = 16
    strengths: list[str]
    maturity_gaps: list[str]
    evidence_limitations: list[str]
    radar: list[DomainRadarPoint]
    heatmap: list[HeatmapCell]
    improvement_actions: list[ImprovementActionOut]
    chart_summary: str
    scores: dict[str, float]
    enterprise_standards: dict | None = None
    detailed_review: dict | None = None
    detailed_review_incomplete: bool = False
    # Never include ai_candidate_score or numeric enterprise alignment score here


class AdminPublishedComparisonOut(StrictSchema):
    assessment_id: str
    version: int
    ai_vs_final: list[dict]
    overall_maturity: float | None = None
