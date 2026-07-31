from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MaturityLevel(StrictModel):
    score: float = Field(ge=1.0, le=5.0)
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)


class ScoreConfig(StrictModel):
    minimum: float = 1.0
    maximum: float = 5.0
    allow_decimals: bool = True
    decimal_places: int = Field(default=1, ge=0, le=2)

    @model_validator(mode="after")
    def _bounds(self) -> ScoreConfig:
        if self.minimum != 1.0 or self.maximum != 5.0:
            raise ValueError("score range must be 1.0 to 5.0")
        if not self.allow_decimals and self.decimal_places != 0:
            raise ValueError("decimal_places must be 0 when decimals are disabled")
        return self


class RubricLevel(StrictModel):
    level: float = Field(ge=1.0, le=5.0)
    description: str = Field(min_length=1, max_length=1000)


class EvidenceMapping(StrictModel):
    signal: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    weight: Literal["primary", "supporting", "contextual"] = "supporting"


class QuestionSeed(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    intent: str = Field(min_length=1, max_length=500)


class ClarificationSeed(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    when: str = Field(min_length=1, max_length=120)


class PracticeConfig(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=120)
    order: int = Field(ge=0)
    hidden_from_participants: bool = True
    summary: str = Field(min_length=1, max_length=1000)
    required_evaluation_dimensions: list[str] = Field(min_length=1)
    maturity_rubric: list[RubricLevel] = Field(min_length=5, max_length=5)
    possible_evidence_signals: list[str] = Field(min_length=1)
    jira_evidence_mappings: list[EvidenceMapping] = Field(default_factory=list)
    ado_evidence_mappings: list[EvidenceMapping] = Field(default_factory=list)
    question_seeds: list[QuestionSeed] = Field(min_length=1)
    clarification_seeds: list[ClarificationSeed] = Field(min_length=1)
    improvement_guidance: list[str] = Field(min_length=1)
    kpi_guidance: list[str] = Field(min_length=1)

    @field_validator("maturity_rubric")
    @classmethod
    def _rubric_levels(cls, value: list[RubricLevel]) -> list[RubricLevel]:
        levels = sorted(item.level for item in value)
        expected = [1.0, 2.0, 3.0, 4.0, 5.0]
        if levels != expected:
            raise ValueError("maturity_rubric must define levels 1.0 through 5.0 exactly once each")
        return value


class DomainConfig(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=120)
    short_name: str = Field(min_length=1, max_length=16)
    order: int = Field(ge=0)
    description: str = Field(min_length=1, max_length=1000)
    practices: list[PracticeConfig] = Field(min_length=1)


class StopCriteria(StrictModel):
    min_practices_with_sufficient_coverage: int = Field(ge=1, le=16)
    max_clarification_rounds_per_practice: int = Field(ge=0, le=10)
    max_interview_turns: int = Field(ge=1, le=200)
    min_overall_confidence: float = Field(ge=0.0, le=1.0)
    require_all_domains_touched: bool = True


class EvidenceInfluencePolicy(StrictModel):
    description: str = Field(min_length=1, max_length=500)
    conversation_weight: float = Field(ge=0.0, le=1.0)
    evidence_weight: float = Field(ge=0.0, le=1.0)
    allow_evidence_to_raise_score: bool
    allow_evidence_to_lower_score: bool

    @model_validator(mode="after")
    def _weights(self) -> EvidenceInfluencePolicy:
        total = round(self.conversation_weight + self.evidence_weight, 4)
        if total != 1.0:
            raise ValueError("conversation_weight + evidence_weight must equal 1.0")
        return self


class ModelDefaults(StrictModel):
    assessment_model: str = Field(min_length=1, max_length=120)
    transcription_model: str = Field(min_length=1, max_length=120)
    reasoning_effort: str = Field(min_length=1, max_length=40)
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(ge=256, le=16000)


class VoiceDefaults(StrictModel):
    enabled: bool = True
    language: str = Field(min_length=2, max_length=32)
    interim_results: bool = True
    max_utterance_seconds: int = Field(ge=10, le=600)
    silence_timeout_ms: int = Field(ge=200, le=10000)


class PromptTemplates(StrictModel):
    next_best_question: str = Field(min_length=1)
    clarification: str = Field(min_length=1)
    coverage_analysis: str = Field(min_length=1)
    candidate_scoring: str = Field(min_length=1)
    improvement_plan: str = Field(min_length=1)


class AssessmentModelConfig(StrictModel):
    version: str = Field(min_length=1, max_length=32)
    schema_name: Literal["safe_devops_adaptive_assessment"]
    description: str = Field(min_length=1, max_length=2000)
    maturity_levels: list[MaturityLevel] = Field(min_length=5, max_length=5)
    score: ScoreConfig
    required_evaluation_dimensions: list[str] = Field(min_length=1)
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    stop_criteria: StopCriteria
    evidence_influence_policies: dict[str, EvidenceInfluencePolicy]
    model_defaults: ModelDefaults
    voice_defaults: VoiceDefaults
    prompt_templates: PromptTemplates
    domains: list[DomainConfig] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def _validate_model(self) -> AssessmentModelConfig:
        expected_policies = {"context_only", "balanced", "evidence_led"}
        if set(self.evidence_influence_policies) != expected_policies:
            raise ValueError(f"evidence_influence_policies must be exactly {sorted(expected_policies)}")

        level_scores = sorted(level.score for level in self.maturity_levels)
        if level_scores != [1.0, 2.0, 3.0, 4.0, 5.0]:
            raise ValueError("maturity_levels must define scores 1.0 through 5.0 exactly once each")

        domain_keys: set[str] = set()
        practice_keys: set[str] = set()
        practice_count = 0
        for domain in sorted(self.domains, key=lambda item: item.order):
            if domain.key in domain_keys:
                raise ValueError(f"duplicate domain key: {domain.key}")
            domain_keys.add(domain.key)
            orders = [practice.order for practice in domain.practices]
            if len(orders) != len(set(orders)):
                raise ValueError(f"duplicate practice order in domain {domain.key}")
            for practice in domain.practices:
                practice_count += 1
                if practice.key in practice_keys:
                    raise ValueError(f"duplicate practice key: {practice.key}")
                practice_keys.add(practice.key)
                missing_dims = set(self.required_evaluation_dimensions) - set(practice.required_evaluation_dimensions)
                if missing_dims:
                    raise ValueError(
                        f"practice {practice.key} missing required evaluation dimensions: {sorted(missing_dims)}"
                    )

        if practice_count != 16:
            raise ValueError(f"expected exactly 16 practices, found {practice_count}")

        domain_orders = [domain.order for domain in self.domains]
        if len(domain_orders) != len(set(domain_orders)):
            raise ValueError("domain order values must be unique")

        return self

    def ordered_domains(self) -> list[DomainConfig]:
        return sorted(self.domains, key=lambda item: item.order)

    def ordered_practices(self) -> list[tuple[DomainConfig, PracticeConfig]]:
        result: list[tuple[DomainConfig, PracticeConfig]] = []
        for domain in self.ordered_domains():
            for practice in sorted(domain.practices, key=lambda item: item.order):
                result.append((domain, practice))
        return result

    def practice_keys(self) -> set[str]:
        return {practice.key for practice in (p for _, p in self.ordered_practices())}

    def require_practice(self, practice_key: str) -> PracticeConfig:
        for _, practice in self.ordered_practices():
            if practice.key == practice_key:
                return practice
        raise ValueError(f"unknown practice key: {practice_key}")
