from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.http import sanitize_remote_text
from app.models import Assessment, AssessmentReview, ImprovementAction, InterviewTurn, PracticeCoverage
from app.models.ai_settings import InterviewSession
from app.models.enums import AssessmentStatus, CoverageState
from app.openai.scoring_mock import MockScoringProvider
from app.schemas.scoring import CandidateScoringAI, DomainRadarPoint, HeatmapCell, PracticeReviewOut
from app.services.ai_settings import AiSettingsService
from app.services.audit import AuditService
from app.services.evidence import EvidenceService
from app.services.lifecycle import LifecycleService


class ScoringService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.model = get_assessment_model_config()
        self.audit = AuditService(db)
        self.lifecycle = LifecycleService(db)
        self.evidence = EvidenceService(db)
        self.ai = AiSettingsService(db)

    def enter_admin_review(self, assessment_id: str, *, actor: str = "admin") -> AssessmentReview:
        assessment = self._require(assessment_id)
        status = AssessmentStatus(assessment.status)
        if status == AssessmentStatus.INTERVIEW_COMPLETE:
            self.lifecycle.transition(assessment, AssessmentStatus.ADMIN_REVIEW, actor_subject=actor)
        elif status != AssessmentStatus.ADMIN_REVIEW:
            if status == AssessmentStatus.PUBLISHED:
                self.lifecycle.transition(assessment, AssessmentStatus.ADMIN_REVIEW, actor_subject=actor)
            else:
                raise AppError(
                    code="invalid_state",
                    message="Assessment must be interview_complete (or published for correction) to enter admin review",
                    status_code=409,
                )
        return self.generate_candidate_scores(assessment_id, actor=actor)

    def generate_candidate_scores(self, assessment_id: str, *, actor: str = "admin") -> AssessmentReview:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(code="invalid_state", message="Candidate scoring requires admin_review", status_code=409)

        context = self._build_context(assessment)
        provider = self._provider()
        try:
            result, telemetry = provider.score_assessment(context)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                code="scoring_failed",
                message="Failed to generate candidate scores",
                status_code=502,
                details={"error_type": type(exc).__name__},
            ) from exc

        result = self._validate(result)
        ai_settings = self.ai.get()
        prompt_version = self.model.version
        model_name = telemetry.get("model") or ai_settings.assessment_model

        by_key = {c.practice_key: c for c in assessment.practice_coverages}
        for item in result.practice_scores:
            coverage = by_key.get(item.practice_key)
            if coverage is None:
                continue
            coverage.coverage_state = item.coverage_state
            coverage.ai_candidate_score = float(item.ai_candidate_score)
            # Do not overwrite an existing admin final during regeneration.
            coverage.named_maturity_level = item.named_maturity_level
            coverage.confidence = float(item.confidence)
            coverage.human_evidence = sanitize_remote_text(item.human_evidence, max_len=4000)
            coverage.jira_evidence = sanitize_remote_text(item.jira_evidence, max_len=4000)
            coverage.ado_evidence = sanitize_remote_text(item.ado_evidence, max_len=4000)
            coverage.source_turn_ids_json = json.dumps(item.source_turn_ids[:20])
            coverage.contradictions_json = json.dumps(
                [sanitize_remote_text(c, max_len=400) for c in item.contradictions][:12]
            )
            coverage.limitations_json = json.dumps(
                [sanitize_remote_text(c, max_len=400) for c in item.limitations][:12]
            )
            coverage.missing_information_json = json.dumps(
                [sanitize_remote_text(c, max_len=400) for c in item.missing_information][:12]
            )
            coverage.scoring_rationale = sanitize_remote_text(item.rationale, max_len=4000)
            coverage.recommendation_text = sanitize_remote_text(item.recommendation, max_len=2000) or None
            coverage.scoring_model_version = str(model_name)
            coverage.scoring_prompt_version = prompt_version

        # Replace draft improvement actions (unpublished only).
        for action in list(assessment.improvement_actions):
            if not action.is_published:
                self.db.delete(action)
        self.db.flush()
        for action in result.improvement_actions:
            self.db.add(
                ImprovementAction(
                    assessment_id=assessment_id,
                    practice_key=action.practice_key,
                    domain_key=action.domain_key,
                    title=sanitize_remote_text(action.title, max_len=240),
                    detail=sanitize_remote_text(action.recommended_action, max_len=2000),
                    observation=sanitize_remote_text(action.observation, max_len=2000),
                    supporting_evidence=sanitize_remote_text(action.supporting_evidence, max_len=2000),
                    why_it_matters=sanitize_remote_text(action.why_it_matters, max_len=2000),
                    recommended_action=sanitize_remote_text(action.recommended_action, max_len=2000),
                    time_horizon=action.time_horizon,
                    kpi=sanitize_remote_text(action.kpi, max_len=240),
                    priority=action.priority,
                    is_published=False,
                )
            )

        review = self._latest_review(assessment_id)
        if review is None:
            review = AssessmentReview(assessment_id=assessment_id, reviewer_subject=actor)
            self.db.add(review)
        review.reviewer_subject = actor
        review.ready_to_publish = False
        review.scoring_telemetry_json = json.dumps(telemetry)
        review.overall_maturity = float(result.overall_maturity)
        review.confidence_summary = result.confidence_summary
        review.evidence_quality = result.evidence_quality
        review.strengths_json = json.dumps(result.strengths)
        review.maturity_gaps_json = json.dumps(result.maturity_gaps)
        review.limitations_json = json.dumps(result.evidence_limitations)
        review.notes = sanitize_remote_text(result.chart_summary, max_len=2000)
        self.db.flush()

        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.candidate_scores_generated",
            message="Candidate scores generated for admin review",
            actor_type="admin",
            actor_subject=actor,
            details={
                "overall_maturity": result.overall_maturity,
                "model": model_name,
                "prompt_config_version": prompt_version,
                "provider": telemetry.get("provider"),
            },
        )
        return review

    def domain_rollups(self, assessment: Assessment, *, use_final: bool = True) -> list[DomainRadarPoint]:
        points: list[DomainRadarPoint] = []
        by_domain: dict[str, list[float]] = {}
        for coverage in assessment.practice_coverages:
            score = coverage.admin_final_score if use_final and coverage.admin_final_score is not None else coverage.ai_candidate_score
            if score is None:
                continue
            by_domain.setdefault(coverage.domain_key, []).append(float(score))
        for domain in self.model.ordered_domains():
            scores = by_domain.get(domain.key, [])
            avg = round(sum(scores) / len(scores), 1) if scores else 0.0
            points.append(
                DomainRadarPoint(
                    domain_key=domain.key,
                    domain_short_name=domain.short_name,
                    domain_name=domain.name,
                    score=avg,
                    weight=float(domain.weight),
                )
            )
        return points

    def weighted_overall(self, radar: list[DomainRadarPoint]) -> float:
        total_w = sum(p.weight for p in radar if p.score > 0) or 1.0
        weighted = sum(p.score * p.weight for p in radar if p.score > 0)
        return round(weighted / total_w, 1)

    def heatmap(self, assessment: Assessment, *, use_final: bool = True) -> list[HeatmapCell]:
        cells: list[HeatmapCell] = []
        name_by_key = {p.key: p.name for _, p in self.model.ordered_practices()}
        short_by_domain = {d.key: d.short_name for d in self.model.ordered_domains()}
        for coverage in assessment.practice_coverages:
            score = coverage.admin_final_score if use_final and coverage.admin_final_score is not None else coverage.ai_candidate_score
            cells.append(
                HeatmapCell(
                    practice_key=coverage.practice_key,
                    practice_name=name_by_key.get(coverage.practice_key, coverage.practice_key),
                    domain_short_name=short_by_domain.get(coverage.domain_key, coverage.domain_key),
                    score=float(score) if score is not None else None,
                    named_maturity_level=coverage.named_maturity_level,
                )
            )
        return cells

    def practice_out(self, coverage: PracticeCoverage) -> PracticeReviewOut:
        name_by_key = {p.key: p.name for _, p in self.model.ordered_practices()}
        short_by_domain = {d.key: d.short_name for d in self.model.ordered_domains()}
        return PracticeReviewOut(
            practice_key=coverage.practice_key,
            practice_name=name_by_key.get(coverage.practice_key, coverage.practice_key),
            domain_key=coverage.domain_key,
            domain_short_name=short_by_domain.get(coverage.domain_key, coverage.domain_key),
            coverage_state=coverage.coverage_state,
            ai_candidate_score=coverage.ai_candidate_score,
            named_maturity_level=coverage.named_maturity_level,
            confidence=coverage.confidence,
            human_evidence=coverage.human_evidence or "",
            jira_evidence=coverage.jira_evidence or "",
            ado_evidence=coverage.ado_evidence or "",
            source_turn_ids=json.loads(coverage.source_turn_ids_json or "[]"),
            contradictions=json.loads(coverage.contradictions_json or "[]"),
            limitations=json.loads(coverage.limitations_json or "[]"),
            scoring_rationale=coverage.scoring_rationale or "",
            missing_information=json.loads(coverage.missing_information_json or "[]"),
            admin_final_score=coverage.admin_final_score,
            admin_rationale=coverage.admin_rationale,
            evidence_unreliable=bool(coverage.evidence_unreliable),
            admin_observation=coverage.admin_observation,
            recommendation_text=coverage.recommendation_text,
        )

    def _validate(self, result: CandidateScoringAI) -> CandidateScoringAI:
        known = self.model.practice_keys()
        levels = {lvl.name for lvl in self.model.maturity_levels}
        cleaned = []
        for item in result.practice_scores:
            if item.practice_key not in known:
                raise AppError(
                    code="unknown_practice_key",
                    message=f"Scoring model returned unknown practice: {item.practice_key}",
                    status_code=502,
                )
            if not (1.0 <= item.ai_candidate_score <= 5.0):
                raise AppError(code="invalid_score_range", message="Score out of 1.0–5.0 range", status_code=502)
            level = item.named_maturity_level if item.named_maturity_level in levels else self._nearest_level_name(item.ai_candidate_score)
            cleaned.append(item.model_copy(update={"named_maturity_level": level}))
        for action in result.improvement_actions:
            if action.practice_key not in known:
                raise AppError(code="unknown_practice_key", message="Improvement references unknown practice", status_code=502)
            required = [
                action.observation,
                action.supporting_evidence,
                action.why_it_matters,
                action.recommended_action,
                action.kpi,
            ]
            if not all(str(v).strip() for v in required):
                raise AppError(code="incomplete_improvement_action", message="Improvement action missing required fields", status_code=502)
        return result.model_copy(update={"practice_scores": cleaned})

    def _nearest_level_name(self, score: float) -> str:
        nearest = min(self.model.maturity_levels, key=lambda lvl: abs(lvl.score - score))
        return nearest.name

    def _provider(self):
        ai = self.ai.get()
        if ai.interview_provider == "live" and self.settings.openai_api_key:
            from app.openai.scoring_live import LiveScoringProvider

            return LiveScoringProvider(
                api_key=self.settings.openai_api_key,
                model=ai.assessment_model,
                reasoning_effort=ai.reasoning_effort,
            )
        return MockScoringProvider()

    def _build_context(self, assessment: Assessment) -> dict[str, Any]:
        turns = list(
            self.db.scalars(
                select(InterviewTurn)
                .where(InterviewTurn.assessment_id == assessment.id)
                .order_by(InterviewTurn.sequence.asc())
            )
        )
        source_turn_ids: dict[str, list[str]] = {}
        for coverage in assessment.practice_coverages:
            source_turn_ids[coverage.practice_key] = json.loads(coverage.source_turn_ids_json or "[]")

        limitations: list[str] = []
        integration_failures: list[str] = []
        jira_failed = False
        ado_failed = False
        try:
            snapshot = self.evidence.get_latest_snapshot(assessment.id)
            if snapshot:
                for lim in snapshot.limitations:
                    limitations.append(lim.message)
                    code = (lim.code or "").lower()
                    if "fail" in code or "error" in code or "unavailable" in code:
                        integration_failures.append(lim.message)
                        if (lim.source_system or "").lower() == "jira":
                            jira_failed = True
                        if (lim.source_system or "").lower() in {"ado", "azure_devops", "azdo"}:
                            ado_failed = True
        except Exception:  # noqa: BLE001
            pass

        rubrics = {
            practice.key: [{"level": r.level, "description": r.description} for r in practice.maturity_rubric]
            for _, practice in self.model.ordered_practices()
        }
        domain_weights = {d.key: d.weight for d in self.model.ordered_domains()}
        return {
            "team_name": assessment.team_name,
            "product_service_name": assessment.product_service_name,
            "lookback_days": assessment.lookback_days,
            "influence_mode": assessment.evidence_influence_mode,
            "coverage_states": {c.practice_key: c.coverage_state for c in assessment.practice_coverages},
            "source_turn_ids": source_turn_ids,
            "answers": [
                {
                    "id": t.id,
                    "question": t.question_text,
                    "answer": t.answer_text,
                    "source": t.source,
                    "practice_keys": json.loads(t.practice_keys_json or "[]"),
                }
                for t in turns
                if t.answer_text
            ],
            "rubrics": rubrics,
            "domain_weights": domain_weights,
            "maturity_levels": [lvl.model_dump() for lvl in self.model.maturity_levels],
            "evidence_limitations": limitations,
            "integration_failures": integration_failures,
            "jira_failed": jira_failed,
            "ado_failed": ado_failed,
            "prompt_template": self.model.prompt_templates.candidate_scoring,
        }

    def _latest_review(self, assessment_id: str) -> AssessmentReview | None:
        return self.db.scalar(
            select(AssessmentReview)
            .where(AssessmentReview.assessment_id == assessment_id)
            .order_by(AssessmentReview.created_at.desc())
        )

    def _require(self, assessment_id: str) -> Assessment:
        assessment = self.db.scalar(
            select(Assessment)
            .options(
                selectinload(Assessment.practice_coverages),
                selectinload(Assessment.improvement_actions),
                selectinload(Assessment.reviews),
            )
            .where(Assessment.id == assessment_id)
        )
        if assessment is None:
            raise AppError(code="assessment_not_found", message="Assessment not found", status_code=404)
        return assessment
