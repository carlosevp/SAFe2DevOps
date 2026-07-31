from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin
from app.models.enums import AssessmentStatus
from app.schemas.assessment import (
    AdminScoreUpdate,
    AssessmentCreate,
    AssessmentSourceSelectionIn,
    AssessmentSummary,
    LifecycleTransitionRequest,
    PracticeCoverageAdmin,
    PracticeCoverageParticipant,
    PublishedReportOut,
)
from app.services.assessment import AssessmentService
from app.services.lifecycle import LifecycleService
from app.services.publication import PublicationService

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", response_model=AssessmentSummary)
def create_assessment(
    body: AssessmentCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    service = AssessmentService(db)
    assessment = service.create(**body.model_dump())
    db.commit()
    return AssessmentSummary.model_validate(assessment)


@router.get("", response_model=list[AssessmentSummary])
def list_assessments(
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> list[AssessmentSummary]:
    service = AssessmentService(db)
    return [AssessmentSummary.model_validate(item) for item in service.repo.list_all()]


@router.post("/{assessment_id}/source-selection", response_model=AssessmentSummary)
def set_source_selection(
    assessment_id: str,
    body: AssessmentSourceSelectionIn,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    service = AssessmentService(db)
    service.set_source_selection(assessment_id, body.model_dump())
    assessment = service.repo.get(assessment_id)
    db.commit()
    assert assessment is not None
    return AssessmentSummary.model_validate(assessment)


@router.post("/{assessment_id}/transition", response_model=AssessmentSummary)
def transition_assessment(
    assessment_id: str,
    body: LifecycleTransitionRequest,
    admin: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    service = AssessmentService(db)
    assessment = service._require(assessment_id)
    LifecycleService(db).transition(assessment, body.status, actor_subject=admin.get("subject", "admin"))
    db.commit()
    return AssessmentSummary.model_validate(assessment)


@router.get("/{assessment_id}/coverage/participant", response_model=list[PracticeCoverageParticipant])
def participant_coverage(assessment_id: str, db: Session = Depends(get_db_session)) -> list[PracticeCoverageParticipant]:
    service = AssessmentService(db)
    assessment = service._require(assessment_id)
    result: list[PracticeCoverageParticipant] = []
    for coverage in assessment.practice_coverages:
        result.append(
            PracticeCoverageParticipant(
                practice_key=coverage.practice_key,
                domain_key=coverage.domain_key,
                coverage_state=coverage.coverage_state,
                open_gaps=json.loads(coverage.open_gaps_json or "[]"),
                confidence=coverage.confidence,
            )
        )
    return result


@router.get("/{assessment_id}/coverage/admin", response_model=list[PracticeCoverageAdmin])
def admin_coverage(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> list[PracticeCoverageAdmin]:
    service = AssessmentService(db)
    assessment = service._require(assessment_id)
    result: list[PracticeCoverageAdmin] = []
    for coverage in assessment.practice_coverages:
        result.append(
            PracticeCoverageAdmin(
                practice_key=coverage.practice_key,
                domain_key=coverage.domain_key,
                coverage_state=coverage.coverage_state,
                open_gaps=json.loads(coverage.open_gaps_json or "[]"),
                confidence=coverage.confidence,
                evidence_summaries=json.loads(coverage.evidence_summaries_json or "[]"),
                source_turn_ids=json.loads(coverage.source_turn_ids_json or "[]"),
                contradictions=json.loads(coverage.contradictions_json or "[]"),
                ai_candidate_score=coverage.ai_candidate_score,
                admin_final_score=coverage.admin_final_score,
                admin_rationale=coverage.admin_rationale,
            )
        )
    return result


@router.put("/{assessment_id}/coverage/{practice_key}/admin-score", response_model=PracticeCoverageAdmin)
def update_admin_score(
    assessment_id: str,
    practice_key: str,
    body: AdminScoreUpdate,
    admin: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> PracticeCoverageAdmin:
    service = AssessmentService(db)
    coverage = service.set_admin_score(
        assessment_id,
        practice_key,
        score=body.score,
        rationale=body.rationale,
        actor_subject=admin.get("subject", "admin"),
    )
    db.commit()
    return PracticeCoverageAdmin(
        practice_key=coverage.practice_key,
        domain_key=coverage.domain_key,
        coverage_state=coverage.coverage_state,
        open_gaps=json.loads(coverage.open_gaps_json or "[]"),
        confidence=coverage.confidence,
        evidence_summaries=json.loads(coverage.evidence_summaries_json or "[]"),
        source_turn_ids=json.loads(coverage.source_turn_ids_json or "[]"),
        contradictions=json.loads(coverage.contradictions_json or "[]"),
        ai_candidate_score=coverage.ai_candidate_score,
        admin_final_score=coverage.admin_final_score,
        admin_rationale=coverage.admin_rationale,
    )


@router.post("/{assessment_id}/publish", response_model=PublishedReportOut)
def publish_assessment(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> PublishedReportOut:
    report = PublicationService(db).publish(assessment_id, published_by=admin.get("subject", "admin"))
    db.commit()
    return PublishedReportOut(
        id=report.id,
        assessment_id=report.assessment_id,
        version=report.version,
        title=report.title,
        summary_markdown=report.summary_markdown,
        scores=json.loads(report.scores_json),
        published_by=report.published_by,
        published_at=report.published_at,
        immutable=True,
    )


@router.get("/status-values", response_model=list[str])
def status_values() -> list[str]:
    return [status.value for status in AssessmentStatus]
