from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CoverageState


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PracticeUpdateAI(StrictSchema):
    """Model-produced practice update. Candidate scores are stored server-side only."""

    practice_key: str = Field(min_length=1, max_length=64)
    coverage_state: CoverageState
    evidence_summary: str = Field(default="", max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    open_gaps: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    candidate_score: float | None = Field(default=None, ge=1.0, le=5.0)


class InterviewAnalysisAI(StrictSchema):
    """Strict Structured Outputs schema for post-answer analysis."""

    response_summary: str = Field(min_length=1, max_length=4000)
    claims: list[str] = Field(default_factory=list)
    source_attribution: list[str] = Field(default_factory=list)
    practice_updates: list[PracticeUpdateAI] = Field(default_factory=list)
    evidence_summary: str = Field(default="", max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)
    open_gaps: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    needs_immediate_clarification: bool
    clarification_question: str | None = Field(default=None, max_length=2000)
    next_best_question: str = Field(min_length=1, max_length=4000)
    reason_for_next_question: str = Field(min_length=1, max_length=2000)
    completion_recommendation: Literal["continue", "checkpoint", "complete"] = "continue"
    overall_coverage_summary: str = Field(min_length=1, max_length=4000)


class OpeningQuestionAI(StrictSchema):
    question_text: str = Field(min_length=1, max_length=4000)
    why_asking: str = Field(min_length=1, max_length=2000)
    evidence_context: str = Field(min_length=1, max_length=2000)
    topic_label: str = Field(default="Delivery journey", max_length=80)


class PracticeCoveragePublic(StrictSchema):
    practice_key: str
    practice_name: str
    domain_key: str
    domain_short_name: str
    coverage_state: CoverageState
    open_gaps: list[str] = Field(default_factory=list)
    # confidence is ok for host workshop; scores are never included


class InterviewTelemetryOut(StrictSchema):
    provider: str
    model: str
    reasoning_effort: str
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    prompt_config_version: str


class InterviewSessionOut(StrictSchema):
    assessment_id: str
    team_name: str
    product_service_name: str
    status: str
    interview_status: str
    current_question: str
    why_asking: str
    evidence_context: str
    topic_label: str
    pending_clarification: str | None = None
    draft_answer_text: str = ""
    last_outcome: Literal["none", "clarify", "sufficient"] = "none"
    overall_coverage_summary: str = ""
    coverage_confirmation: str | None = None
    turn_count: int
    answered_turn_count: int
    completion_eligible: bool
    completion_blockers: list[str] = Field(default_factory=list)
    practices: list[PracticeCoveragePublic] = Field(default_factory=list)
    telemetry: InterviewTelemetryOut | None = None
    # Explicitly never include scores


class TurnSubmitIn(StrictSchema):
    answer_text: str = Field(min_length=1, max_length=20000)
    idempotency_key: str = Field(min_length=8, max_length=120)
    is_clarification: bool = False


class DraftSaveIn(StrictSchema):
    draft_answer_text: str = Field(default="", max_length=20000)


class TurnSubmitOut(StrictSchema):
    session: InterviewSessionOut
    analysis_summary: str
    claims: list[str] = Field(default_factory=list)
    covered_practices: list[str] = Field(default_factory=list)
    partial_practices: list[str] = Field(default_factory=list)
    clarify_practices: list[str] = Field(default_factory=list)
    duplicated: bool = False


class CheckpointOut(StrictSchema):
    assessment_id: str
    headline: str
    summary: str
    sufficient_count: int
    partial_count: int
    not_discussed_count: int
    clarify_count: int
    covered: list[dict[str, str]] = Field(default_factory=list)
    remaining: list[dict[str, str]] = Field(default_factory=list)
    completion_eligible: bool
    completion_blockers: list[str] = Field(default_factory=list)
    impact_note: str


class AiSettingsOut(StrictSchema):
    assessment_model: str
    reasoning_effort: str
    interview_provider: Literal["mock", "live"]
    transcription_model: str
    prompt_config_version: str
    available_models: list[str]
    available_reasoning_efforts: list[str]
    updated_at: datetime | None = None


class AiSettingsUpdate(StrictSchema):
    assessment_model: str | None = None
    reasoning_effort: str | None = None
    interview_provider: Literal["mock", "live"] | None = None


class InterviewStartOut(StrictSchema):
    session: InterviewSessionOut
