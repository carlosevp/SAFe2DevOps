from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Assessment
from app.models.enums import AssessmentStatus
from app.repositories.assessment import AssessmentRepository
from app.services.audit import AuditService

ALLOWED_TRANSITIONS: dict[AssessmentStatus, set[AssessmentStatus]] = {
    AssessmentStatus.SETUP: {AssessmentStatus.COLLECTING_EVIDENCE, AssessmentStatus.ARCHIVED},
    AssessmentStatus.COLLECTING_EVIDENCE: {
        AssessmentStatus.EVIDENCE_READY,
        AssessmentStatus.SETUP,
        AssessmentStatus.ARCHIVED,
    },
    AssessmentStatus.EVIDENCE_READY: {
        AssessmentStatus.INTERVIEW_ACTIVE,
        AssessmentStatus.COLLECTING_EVIDENCE,
        AssessmentStatus.ARCHIVED,
    },
    AssessmentStatus.INTERVIEW_ACTIVE: {
        AssessmentStatus.INTERVIEW_COMPLETE,
        AssessmentStatus.EVIDENCE_READY,
        AssessmentStatus.ARCHIVED,
    },
    AssessmentStatus.INTERVIEW_COMPLETE: {
        AssessmentStatus.ADMIN_REVIEW,
        AssessmentStatus.INTERVIEW_ACTIVE,
        AssessmentStatus.ARCHIVED,
    },
    AssessmentStatus.ADMIN_REVIEW: {
        AssessmentStatus.PUBLISHED,
        AssessmentStatus.INTERVIEW_COMPLETE,
        AssessmentStatus.ARCHIVED,
    },
    AssessmentStatus.PUBLISHED: {AssessmentStatus.ARCHIVED},
    AssessmentStatus.ARCHIVED: set(),
}


class LifecycleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentRepository(db)
        self.audit = AuditService(db)

    def transition(
        self,
        assessment: Assessment,
        new_status: AssessmentStatus | str,
        *,
        actor_subject: str = "system",
    ) -> Assessment:
        target = AssessmentStatus(new_status)
        current = AssessmentStatus(assessment.status)
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise AppError(
                code="invalid_lifecycle_transition",
                message=f"Cannot transition assessment from {current.value} to {target.value}",
                status_code=409,
                details={"from": current.value, "to": target.value},
            )

        assessment.status = target.value
        if target == AssessmentStatus.PUBLISHED:
            assessment.published_at = datetime.now(UTC)
        if target == AssessmentStatus.ARCHIVED:
            assessment.archived_at = datetime.now(UTC)

        self.audit.record(
            assessment_id=assessment.id,
            event_type="assessment.lifecycle_transition",
            message=f"Assessment moved from {current.value} to {target.value}",
            actor_type="admin" if actor_subject != "system" else "system",
            actor_subject=actor_subject,
            details={"from": current.value, "to": target.value},
        )
        self.db.flush()
        return assessment
