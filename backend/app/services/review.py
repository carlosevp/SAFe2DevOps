from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.core.errors import AppError
from app.integrations.http import sanitize_remote_text
from app.models import Assessment, AssessmentReview, ImprovementAction, PracticeCoverage
from app.models.ai_settings import InterviewSession
from app.models.enums import AssessmentStatus, CoverageState
from app.schemas.scoring import (
    ImprovementActionOut,
    ImprovementEditIn,
    ReviewPackageOut,
)
from app.services.assessment import AssessmentService
from app.services.audit import AuditService
from app.services.lifecycle import LifecycleService
from app.services.scoring import ScoringService


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.scoring = ScoringService(db)
        self.assessments = AssessmentService(db)
        self.lifecycle = LifecycleService(db)
        self.audit = AuditService(db)
        self.model = get_assessment_model_config()

    def get_package(self, assessment_id: str) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        review = self._latest_review(assessment_id)
        radar = self.scoring.domain_rollups(assessment, use_final=True)
        overall = (
            review.overall_maturity
            if review and review.overall_maturity is not None
            else self.scoring.weighted_overall(radar)
        )
        actions = [
            ImprovementActionOut(
                id=a.id,
                title=a.title,
                practice_key=a.practice_key,
                domain_key=a.domain_key,
                observation=a.observation,
                supporting_evidence=a.supporting_evidence,
                why_it_matters=a.why_it_matters,
                recommended_action=a.recommended_action or a.detail,
                time_horizon=a.time_horizon,
                kpi=a.kpi,
                priority=a.priority,
            )
            for a in assessment.improvement_actions
            if not a.is_published
            or AssessmentStatus(assessment.status) == AssessmentStatus.ADMIN_REVIEW
        ]
        ai_vs_final = [
            {
                "practice_key": c.practice_key,
                "ai_candidate_score": c.ai_candidate_score,
                "admin_final_score": c.admin_final_score,
                "admin_rationale": c.admin_rationale,
            }
            for c in assessment.practice_coverages
        ]
        return ReviewPackageOut(
            assessment_id=assessment.id,
            team_name=assessment.team_name,
            product_service_name=assessment.product_service_name,
            status=assessment.status,
            lookback_days=assessment.lookback_days,
            evidence_influence_mode=assessment.evidence_influence_mode,
            overall_maturity=overall,
            confidence_summary=review.confidence_summary if review else None,
            evidence_quality=review.evidence_quality if review else None,
            strengths=json.loads(review.strengths_json) if review else [],
            maturity_gaps=json.loads(review.maturity_gaps_json) if review else [],
            evidence_limitations=json.loads(review.limitations_json) if review else [],
            practices=[self.scoring.practice_out(c) for c in assessment.practice_coverages],
            improvement_actions=actions,
            radar=radar,
            heatmap=self.scoring.heatmap(assessment, use_final=True),
            chart_summary=review.notes or "" if review else "",
            prompt_config_version=self.model.version,
            model_name=next(
                (
                    c.scoring_model_version
                    for c in assessment.practice_coverages
                    if c.scoring_model_version
                ),
                None,
            ),
            ready_to_publish=bool(review.ready_to_publish) if review else False,
            ai_vs_final=ai_vs_final,
        )

    def start_review(self, assessment_id: str, *, actor: str) -> ReviewPackageOut:
        self.scoring.enter_admin_review(assessment_id, actor=actor)
        self.db.flush()
        return self.get_package(assessment_id)

    def accept_or_adjust_score(
        self,
        assessment_id: str,
        practice_key: str,
        *,
        score: float | None,
        rationale: str | None,
        accept_candidate: bool,
        actor: str,
    ) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(
                code="invalid_state",
                message="Scores can only be adjusted during admin review",
                status_code=409,
            )
        coverage = self._coverage(assessment, practice_key)
        if accept_candidate:
            if coverage.ai_candidate_score is None:
                raise AppError(
                    code="no_candidate_score",
                    message="No candidate score to accept",
                    status_code=400,
                )
            coverage.admin_final_score = float(coverage.ai_candidate_score)
            coverage.admin_rationale = (
                rationale.strip() if rationale else "Accepted AI candidate score"
            )
        else:
            if score is None:
                raise AppError(
                    code="score_required",
                    message="Score is required when not accepting candidate",
                    status_code=400,
                )
            self.assessments.set_admin_score(
                assessment_id,
                practice_key,
                score=score,
                rationale=rationale,
                actor_subject=actor,
            )
        self.db.flush()
        return self.get_package(assessment_id)

    def mark_evidence_unreliable(
        self,
        assessment_id: str,
        practice_key: str,
        *,
        unreliable: bool,
        note: str | None,
        actor: str,
    ) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        coverage = self._coverage(assessment, practice_key)
        coverage.evidence_unreliable = unreliable
        if note:
            coverage.admin_observation = sanitize_remote_text(note, max_len=2000)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.evidence_marked_unreliable",
            message=f"Evidence reliability updated for {practice_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"practice_key": practice_key, "unreliable": unreliable},
        )
        self.db.flush()
        return self.get_package(assessment_id)

    def add_observation(
        self, assessment_id: str, practice_key: str, *, observation: str, actor: str
    ) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        coverage = self._coverage(assessment, practice_key)
        coverage.admin_observation = sanitize_remote_text(observation, max_len=4000)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.observation_added",
            message=f"Admin observation added for {practice_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"practice_key": practice_key},
        )
        self.db.flush()
        return self.get_package(assessment_id)

    def edit_recommendation(
        self,
        assessment_id: str,
        practice_key: str,
        *,
        recommendation_text: str,
        actor: str,
    ) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        coverage = self._coverage(assessment, practice_key)
        coverage.recommendation_text = sanitize_remote_text(recommendation_text, max_len=4000)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.recommendation_edited",
            message=f"Recommendation edited for {practice_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"practice_key": practice_key},
        )
        self.db.flush()
        return self.get_package(assessment_id)

    def edit_improvement(
        self, assessment_id: str, action_id: str, body: ImprovementEditIn, *, actor: str
    ) -> ReviewPackageOut:
        action = self.db.get(ImprovementAction, action_id)
        if action is None or action.assessment_id != assessment_id:
            raise AppError(
                code="improvement_not_found",
                message="Improvement action not found",
                status_code=404,
            )
        for field in (
            "title",
            "observation",
            "supporting_evidence",
            "why_it_matters",
            "recommended_action",
            "time_horizon",
            "kpi",
            "priority",
        ):
            value = getattr(body, field)
            if value is not None:
                if isinstance(value, str):
                    setattr(
                        action,
                        field,
                        sanitize_remote_text(value, max_len=2000 if field != "title" else 240),
                    )
                else:
                    setattr(action, field, value)
        if body.recommended_action is not None:
            action.detail = action.recommended_action
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.improvement_edited",
            message="Improvement action edited",
            actor_type="admin",
            actor_subject=actor,
            details={"action_id": action_id},
        )
        self.db.flush()
        return self.get_package(assessment_id)

    def reopen_topic(
        self, assessment_id: str, practice_key: str, *, actor: str
    ) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(
                code="invalid_state", message="Reopen requires admin_review", status_code=409
            )
        coverage = self._coverage(assessment, practice_key)
        coverage.coverage_state = CoverageState.CLARIFY.value
        practice = self.model.require_practice(practice_key)
        session = self.db.scalar(
            select(InterviewSession).where(InterviewSession.assessment_id == assessment_id)
        )
        if session:
            session.interview_status = "active"
            session.pending_clarification = None
            session.current_question = (
                practice.clarification_seeds[0].text
                if practice.clarification_seeds
                else (f"Let's revisit {practice.name}. What concrete examples can the team share?")
            )
            session.topic_label = practice.name
            session.why_asking = "Admin reopened this unresolved topic during review."
            session.last_outcome = "none"
        self.lifecycle.transition(
            assessment, AssessmentStatus.INTERVIEW_ACTIVE, actor_subject=actor
        )
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.topic_reopened",
            message=f"Reopened unresolved topic for {practice_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"practice_key": practice_key},
        )
        self.db.flush()
        return self.get_package(assessment_id)

    def approve(self, assessment_id: str, *, actor: str) -> ReviewPackageOut:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(
                code="invalid_state", message="Approve requires admin_review", status_code=409
            )
        missing = [
            c.practice_key
            for c in assessment.practice_coverages
            if c.admin_final_score is None and c.ai_candidate_score is None
        ]
        if missing:
            raise AppError(
                code="scores_incomplete",
                message="All practices need scores before approval",
                status_code=400,
                details={"missing": missing},
            )
        # Accept remaining candidate scores that were not explicitly finalized.
        for coverage in assessment.practice_coverages:
            if coverage.admin_final_score is None and coverage.ai_candidate_score is not None:
                coverage.admin_final_score = coverage.ai_candidate_score
                coverage.admin_rationale = (
                    coverage.admin_rationale or "Accepted AI candidate score on approve"
                )
        review = self._latest_review(assessment_id)
        if review is None:
            review = AssessmentReview(assessment_id=assessment_id, reviewer_subject=actor)
            self.db.add(review)
        review.ready_to_publish = True
        review.approved_at = datetime.now(UTC)
        review.reviewer_subject = actor
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.review_approved",
            message="Admin approved review package for publication",
            actor_type="admin",
            actor_subject=actor,
        )
        self.db.flush()
        return self.get_package(assessment_id)

    def _coverage(self, assessment: Assessment, practice_key: str) -> PracticeCoverage:
        for coverage in assessment.practice_coverages:
            if coverage.practice_key == practice_key:
                return coverage
        raise AppError(
            code="coverage_missing", message="Practice coverage not found", status_code=404
        )

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
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return assessment
