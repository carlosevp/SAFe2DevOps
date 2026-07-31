from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.assessment_config import get_assessment_model_config
from app.core.errors import AppError
from app.models import Assessment, AssessmentSourceSelection, PracticeCoverage
from app.models.enums import (
    AssessmentStatus,
    CoverageState,
    EvidenceInfluenceMode,
    ParticipationMode,
)
from app.repositories.assessment import AssessmentRepository
from app.services.audit import AuditService
from app.services.lifecycle import LifecycleService


class AssessmentService:
    LOOKBACK_MIN = 30
    LOOKBACK_MAX = 365

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AssessmentRepository(db)
        self.lifecycle = LifecycleService(db)
        self.audit = AuditService(db)
        self.model = get_assessment_model_config()

    def create(
        self,
        *,
        team_name: str,
        product_service_name: str,
        owner_name: str,
        owner_email: str,
        description: str | None = None,
        value_stream: str | None = None,
        lookback_days: int = 90,
        evidence_influence_mode: EvidenceInfluenceMode | str = EvidenceInfluenceMode.BALANCED,
        participation_mode: ParticipationMode | str = ParticipationMode.HYBRID_REMOTE,
    ) -> Assessment:
        self._validate_lookback(lookback_days)
        influence = EvidenceInfluenceMode(evidence_influence_mode)
        if influence.value not in self.model.evidence_influence_policies:
            raise AppError(
                code="invalid_influence_mode",
                message="Unknown evidence influence mode",
                status_code=400,
            )

        assessment = Assessment(
            team_name=team_name,
            product_service_name=product_service_name,
            description=description,
            value_stream=value_stream,
            owner_name=owner_name,
            owner_email=owner_email,
            lookback_days=lookback_days,
            evidence_influence_mode=influence.value,
            participation_mode=ParticipationMode(participation_mode).value,
            status=AssessmentStatus.SETUP.value,
        )
        self.repo.add(assessment)
        self._initialize_practice_coverage(assessment)
        self.audit.record(
            assessment_id=assessment.id,
            event_type="assessment.created",
            message="Assessment created",
            actor_type="admin",
            details={
                "team_name": team_name,
                "lookback_days": lookback_days,
                "evidence_influence_mode": influence.value,
            },
        )
        return assessment

    def set_source_selection(
        self, assessment_id: str, payload: dict[str, Any]
    ) -> AssessmentSourceSelection:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) not in {
            AssessmentStatus.SETUP,
            AssessmentStatus.COLLECTING_EVIDENCE,
        }:
            raise AppError(
                code="invalid_state",
                message="Source selection locked for current status",
                status_code=409,
            )

        pipelines = payload.get("selected_pipelines") or []
        selection = assessment.source_selection or AssessmentSourceSelection(
            assessment_id=assessment.id
        )
        selection.jira_project_key = payload["jira_project_key"]
        selection.jira_project_name = payload.get("jira_project_name")
        selection.jira_board_id = payload.get("jira_board_id")
        selection.jira_board_name = payload.get("jira_board_name")
        selection.jira_jql = payload.get("jira_jql")
        selection.ado_project_id = payload["ado_project_id"]
        selection.ado_project_name = payload.get("ado_project_name")
        selection.ado_repository_id = payload["ado_repository_id"]
        selection.ado_repository_name = payload["ado_repository_name"]
        selection.default_branch = payload.get("default_branch") or "main"
        selection.selected_pipelines_json = json.dumps(pipelines)
        self.repo.add_source_selection(selection)
        return selection

    def set_admin_score(
        self,
        assessment_id: str,
        practice_key: str,
        *,
        score: float,
        rationale: str | None,
        actor_subject: str = "admin",
    ) -> PracticeCoverage:
        self.model.require_practice(practice_key)
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(
                code="invalid_state",
                message="Scores can only be adjusted during admin review",
                status_code=409,
            )

        coverage = self.repo.get_coverage(assessment_id, practice_key)
        if coverage is None:
            raise AppError(
                code="coverage_missing", message="Practice coverage row not found", status_code=404
            )

        if not (1.0 <= score <= 5.0):
            raise AppError(
                code="invalid_score", message="Score must be between 1.0 and 5.0", status_code=400
            )

        material = (
            coverage.ai_candidate_score is None
            or abs(float(coverage.ai_candidate_score) - float(score)) > 1e-9
        )
        if material and not (rationale and rationale.strip()):
            raise AppError(
                code="rationale_required",
                message="Material admin score adjustments require a rationale",
                status_code=400,
            )

        coverage.admin_final_score = float(score)
        coverage.admin_rationale = rationale.strip() if rationale else None
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.score_adjusted",
            message=f"Admin adjusted score for practice {practice_key}",
            actor_type="admin",
            actor_subject=actor_subject,
            details={
                "practice_key": practice_key,
                "admin_final_score": score,
                "had_candidate_score": coverage.ai_candidate_score is not None,
            },
        )
        self.db.flush()
        return coverage

    def _initialize_practice_coverage(self, assessment: Assessment) -> None:
        for domain, practice in self.model.ordered_practices():
            self.repo.upsert_coverage(
                PracticeCoverage(
                    assessment_id=assessment.id,
                    practice_key=practice.key,
                    domain_key=domain.key,
                    coverage_state=CoverageState.NOT_DISCUSSED.value,
                )
            )

    def _validate_lookback(self, lookback_days: int) -> None:
        if lookback_days < self.LOOKBACK_MIN or lookback_days > self.LOOKBACK_MAX:
            raise AppError(
                code="invalid_lookback_days",
                message=f"lookback_days must be between {self.LOOKBACK_MIN} and {self.LOOKBACK_MAX}",
                status_code=400,
                details={"min": self.LOOKBACK_MIN, "max": self.LOOKBACK_MAX},
            )

    def _require(self, assessment_id: str) -> Assessment:
        assessment = self.repo.get(assessment_id)
        if assessment is None:
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return assessment
