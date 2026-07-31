from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin, require_admin_or_dev_mock
from app.models.enums import AssessmentStatus
from app.schemas.assessment import (
    AdminScoreUpdate,
    AssessmentCreate,
    AssessmentSourceSelectionIn,
    AssessmentSummary,
    EvidenceExclusionsIn,
    EvidenceLimitationOut,
    EvidenceMetricOut,
    EvidenceSnapshotOut,
    LifecycleTransitionRequest,
    PracticeCoverageAdmin,
    PracticeCoverageParticipant,
)
from app.schemas.enterprise import (
    StandardFindingOut,
    StandardSnapshotOut,
    TechnologyContextIn,
    TechnologyContextOut,
)
from app.services.assessment import AssessmentService
from app.services.enterprise_standards import EnterpriseStandardsService
from app.services.evidence import EvidenceService
from app.services.lifecycle import LifecycleService

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _snapshot_out(snapshot) -> EvidenceSnapshotOut:
    return EvidenceSnapshotOut(
        id=snapshot.id,
        assessment_id=snapshot.assessment_id,
        lookback_days=snapshot.lookback_days,
        collected_at=snapshot.collected_at,
        jira_project_key=snapshot.jira_project_key,
        ado_repository_name=snapshot.ado_repository_name,
        provenance_summary=snapshot.provenance_summary,
        payload_ref=snapshot.raw_payload_ref,
        payload_checksum=snapshot.payload_checksum,
        quality=snapshot.quality,
        immutable=snapshot.immutable,
        is_representative=snapshot.is_representative,
        metrics=[
            EvidenceMetricOut(
                key=m.key,
                label=m.label,
                value_text=m.value_text,
                value_numeric=m.value_numeric,
                source_system=m.source_system,
                trend=m.trend,
                freshness_label=m.freshness_label,
            )
            for m in snapshot.metrics
        ],
        limitations=[
            EvidenceLimitationOut(
                code=item.code, message=item.message, source_system=item.source_system
            )
            for item in snapshot.limitations
        ],
        exclusions=[item.scope_label for item in snapshot.exclusions],
    )


@router.get("/status-values", response_model=list[str])
def status_values() -> list[str]:
    return [status.value for status in AssessmentStatus]


@router.post("", response_model=AssessmentSummary)
def create_assessment(
    body: AssessmentCreate,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    service = AssessmentService(db)
    assessment = service.create(**body.model_dump())
    db.commit()
    return AssessmentSummary.model_validate(assessment)


@router.get("", response_model=list[AssessmentSummary])
def list_assessments(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[AssessmentSummary]:
    service = AssessmentService(db)
    return [AssessmentSummary.model_validate(item) for item in service.repo.list_all()]


@router.get("/{assessment_id}", response_model=AssessmentSummary)
def get_assessment(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    assessment = AssessmentService(db)._require(assessment_id)
    return AssessmentSummary.model_validate(assessment)


@router.post("/{assessment_id}/source-selection", response_model=AssessmentSummary)
def set_source_selection(
    assessment_id: str,
    body: AssessmentSourceSelectionIn,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    service = AssessmentService(db)
    service.set_source_selection(assessment_id, body.model_dump())
    assessment = service.repo.get(assessment_id)
    db.commit()
    assert assessment is not None
    return AssessmentSummary.model_validate(assessment)


@router.post("/{assessment_id}/evidence/collect", response_model=EvidenceSnapshotOut)
def collect_evidence(
    assessment_id: str,
    refresh: bool = False,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EvidenceSnapshotOut:
    snapshot = EvidenceService(db).collect_snapshot(
        assessment_id, actor=admin.get("subject", "admin"), refresh=refresh
    )
    db.commit()
    return _snapshot_out(snapshot)


@router.get("/{assessment_id}/evidence/latest", response_model=EvidenceSnapshotOut)
def latest_evidence(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EvidenceSnapshotOut:
    snapshot = EvidenceService(db).get_latest_snapshot(assessment_id)
    if snapshot is None:
        from app.core.errors import AppError

        raise AppError(
            code="snapshot_not_found", message="No evidence snapshot yet", status_code=404
        )
    return _snapshot_out(snapshot)


@router.post(
    "/{assessment_id}/evidence/{snapshot_id}/exclusions", response_model=EvidenceSnapshotOut
)
def apply_exclusions(
    assessment_id: str,
    snapshot_id: str,
    body: EvidenceExclusionsIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EvidenceSnapshotOut:
    service = EvidenceService(db)
    snapshot = service.get_snapshot(snapshot_id)
    if snapshot.assessment_id != assessment_id:
        from app.core.errors import AppError

        raise AppError(
            code="snapshot_mismatch",
            message="Snapshot does not belong to assessment",
            status_code=400,
        )
    updated = service.apply_exclusions(
        snapshot_id, body.exclusions, excluded_by=admin.get("subject", "admin")
    )
    db.commit()
    return _snapshot_out(updated)


@router.post("/{assessment_id}/evidence/{snapshot_id}/confirm", response_model=EvidenceSnapshotOut)
def confirm_evidence(
    assessment_id: str,
    snapshot_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EvidenceSnapshotOut:
    service = EvidenceService(db)
    snapshot = service.get_snapshot(snapshot_id)
    if snapshot.assessment_id != assessment_id:
        from app.core.errors import AppError

        raise AppError(
            code="snapshot_mismatch",
            message="Snapshot does not belong to assessment",
            status_code=400,
        )
    confirmed = service.confirm_snapshot(snapshot_id, actor=admin.get("subject", "admin"))
    db.commit()
    return _snapshot_out(confirmed)


@router.post("/{assessment_id}/transition", response_model=AssessmentSummary)
def transition_assessment(
    assessment_id: str,
    body: LifecycleTransitionRequest,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AssessmentSummary:
    service = AssessmentService(db)
    assessment = service._require(assessment_id)
    LifecycleService(db).transition(
        assessment, body.status, actor_subject=admin.get("subject", "admin")
    )
    db.commit()
    return AssessmentSummary.model_validate(assessment)


@router.get(
    "/{assessment_id}/coverage/participant", response_model=list[PracticeCoverageParticipant]
)
def participant_coverage(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[PracticeCoverageParticipant]:
    """Host/admin workshop coverage — never anonymous (scores omitted from schema)."""
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


@router.put(
    "/{assessment_id}/coverage/{practice_key}/admin-score", response_model=PracticeCoverageAdmin
)
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


@router.put(
    "/{assessment_id}/technology-context",
    response_model=TechnologyContextOut,
)
def upsert_technology_context(
    assessment_id: str,
    body: TechnologyContextIn,
    confirm: bool = False,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> TechnologyContextOut:
    out = EnterpriseStandardsService(db).upsert_technology_context(
        assessment_id, body, confirm=confirm
    )
    db.commit()
    return out


@router.get(
    "/{assessment_id}/technology-context",
    response_model=TechnologyContextOut | None,
)
def get_technology_context(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> TechnologyContextOut | None:
    return EnterpriseStandardsService(db).get_technology_context(assessment_id)


@router.get(
    "/{assessment_id}/enterprise-standards/snapshots",
    response_model=list[StandardSnapshotOut],
)
def list_standard_snapshots(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[StandardSnapshotOut]:
    return EnterpriseStandardsService(db).list_snapshots(assessment_id)


@router.get(
    "/{assessment_id}/enterprise-standards/findings",
    response_model=list[StandardFindingOut],
)
def list_standard_findings(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[StandardFindingOut]:
    return EnterpriseStandardsService(db).list_findings(assessment_id)


# Publish endpoint lives on the review router so approve → publish stays cohesive.
