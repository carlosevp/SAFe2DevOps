from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import PublishedReport
from app.models.enums import AssessmentStatus
from app.repositories.assessment import AssessmentRepository
from app.repositories.publication import PublicationRepository
from app.services.audit import AuditService
from app.services.lifecycle import LifecycleService


class PublicationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentRepository(db)
        self.publications = PublicationRepository(db)
        self.lifecycle = LifecycleService(db)
        self.audit = AuditService(db)

    def publish(self, assessment_id: str, *, published_by: str = "admin") -> PublishedReport:
        assessment = self.assessments.get(assessment_id)
        if assessment is None:
            raise AppError(code="assessment_not_found", message="Assessment not found", status_code=404)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(code="invalid_state", message="Assessment must be in admin_review to publish", status_code=409)

        scores: dict[str, float] = {}
        for coverage in assessment.practice_coverages:
            final = coverage.admin_final_score if coverage.admin_final_score is not None else coverage.ai_candidate_score
            if final is None:
                raise AppError(
                    code="scores_incomplete",
                    message="All practices need a final or candidate score before publication",
                    status_code=400,
                )
            scores[coverage.practice_key] = float(final)

        version = self.publications.next_version(assessment_id)
        report = PublishedReport(
            assessment_id=assessment_id,
            version=version,
            title=f"{assessment.team_name} · SAFe DevOps Maturity Report",
            summary_markdown=f"Published maturity report for {assessment.product_service_name}.",
            radar_json=json.dumps({"practices": scores}),
            heatmap_json=json.dumps({"domains": self._domain_heatmap(assessment)}),
            scores_json=json.dumps(scores),
            improvement_plan_json=json.dumps(
                [
                    {
                        "practice_key": action.practice_key,
                        "title": action.title,
                        "detail": action.detail,
                        "priority": action.priority,
                    }
                    for action in assessment.improvement_actions
                ]
            ),
            published_by=published_by,
            published_at=datetime.now(UTC),
            immutable=True,
        )
        self.publications.add(report)
        for action in assessment.improvement_actions:
            action.is_published = True
        self.lifecycle.transition(assessment, AssessmentStatus.PUBLISHED, actor_subject=published_by)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.published",
            message=f"Published report version {version}",
            actor_type="admin",
            actor_subject=published_by,
            details={"version": version},
        )
        return report

    def update_report(self, report_id: str, **_fields: object) -> PublishedReport:
        report = self.publications.get(report_id)
        if report is None:
            raise AppError(code="report_not_found", message="Published report not found", status_code=404)
        if report.immutable:
            raise AppError(
                code="report_immutable",
                message="Published reports are immutable",
                status_code=409,
            )
        raise AppError(code="report_immutable", message="Published reports are immutable", status_code=409)

    @staticmethod
    def _domain_heatmap(assessment) -> dict[str, list[dict[str, float | str]]]:
        grouped: dict[str, list[dict[str, float | str]]] = {}
        for coverage in assessment.practice_coverages:
            score = coverage.admin_final_score if coverage.admin_final_score is not None else coverage.ai_candidate_score
            grouped.setdefault(coverage.domain_key, []).append(
                {"practice_key": coverage.practice_key, "score": float(score or 0)}
            )
        return grouped
