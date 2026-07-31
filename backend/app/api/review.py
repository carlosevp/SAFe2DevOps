from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.schemas.assessment import PublishedReportOut
from app.schemas.scoring import (
    AdminPublishedComparisonOut,
    AdminScoreActionIn,
    ImprovementEditIn,
    MarkUnreliableIn,
    ObservationIn,
    PublishedResultsOut,
    RecommendationIn,
    ReviewPackageOut,
)
from app.services.exports import sanitize_download_name
from app.services.publication import PublicationService
from app.services.review import ReviewService

router = APIRouter(tags=["review"])


@router.post("/assessments/{assessment_id}/review/start", response_model=ReviewPackageOut)
def start_review(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).start_review(assessment_id, actor=admin.get("subject", "admin"))
    db.commit()
    return out


@router.get("/assessments/{assessment_id}/review", response_model=ReviewPackageOut)
def get_review(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    return ReviewService(db).get_package(assessment_id)


@router.post("/assessments/{assessment_id}/review/regenerate", response_model=ReviewPackageOut)
def regenerate_scores(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    ReviewService(db).scoring.generate_candidate_scores(
        assessment_id, actor=admin.get("subject", "admin")
    )
    db.commit()
    return ReviewService(db).get_package(assessment_id)


@router.put(
    "/assessments/{assessment_id}/review/practices/{practice_key}/score",
    response_model=ReviewPackageOut,
)
def set_practice_score(
    assessment_id: str,
    practice_key: str,
    body: AdminScoreActionIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).accept_or_adjust_score(
        assessment_id,
        practice_key,
        score=body.score,
        rationale=body.rationale,
        accept_candidate=body.accept_candidate,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return out


@router.post(
    "/assessments/{assessment_id}/review/practices/{practice_key}/unreliable",
    response_model=ReviewPackageOut,
)
def mark_unreliable(
    assessment_id: str,
    practice_key: str,
    body: MarkUnreliableIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).mark_evidence_unreliable(
        assessment_id,
        practice_key,
        unreliable=body.unreliable,
        note=body.note,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return out


@router.post(
    "/assessments/{assessment_id}/review/practices/{practice_key}/observation",
    response_model=ReviewPackageOut,
)
def add_observation(
    assessment_id: str,
    practice_key: str,
    body: ObservationIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).add_observation(
        assessment_id,
        practice_key,
        observation=body.observation,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return out


@router.put(
    "/assessments/{assessment_id}/review/practices/{practice_key}/recommendation",
    response_model=ReviewPackageOut,
)
def edit_recommendation(
    assessment_id: str,
    practice_key: str,
    body: RecommendationIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).edit_recommendation(
        assessment_id,
        practice_key,
        recommendation_text=body.recommendation_text,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return out


@router.post(
    "/assessments/{assessment_id}/review/practices/{practice_key}/reopen",
    response_model=ReviewPackageOut,
)
def reopen_topic(
    assessment_id: str,
    practice_key: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).reopen_topic(
        assessment_id, practice_key, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.put(
    "/assessments/{assessment_id}/review/improvements/{action_id}",
    response_model=ReviewPackageOut,
)
def edit_improvement(
    assessment_id: str,
    action_id: str,
    body: ImprovementEditIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).edit_improvement(
        assessment_id, action_id, body, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.post("/assessments/{assessment_id}/review/approve", response_model=ReviewPackageOut)
def approve_review(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ReviewPackageOut:
    out = ReviewService(db).approve(assessment_id, actor=admin.get("subject", "admin"))
    db.commit()
    return out


@router.post("/assessments/{assessment_id}/publish", response_model=PublishedReportOut)
def publish_assessment(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> PublishedReportOut:
    report = PublicationService(db).publish(
        assessment_id, published_by=admin.get("subject", "admin")
    )
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


@router.get("/assessments/{assessment_id}/results", response_model=PublishedResultsOut)
def published_results(
    assessment_id: str,
    version: int | None = None,
    db: Session = Depends(get_db_session),
) -> PublishedResultsOut:
    # Hosts and contributors see only published results — no admin auth required.
    return PublicationService(db).get_published_results(assessment_id, version)


@router.get(
    "/assessments/{assessment_id}/results/admin-comparison",
    response_model=AdminPublishedComparisonOut,
)
def admin_comparison(
    assessment_id: str,
    version: int | None = None,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AdminPublishedComparisonOut:
    return PublicationService(db).get_admin_comparison(assessment_id, version)


@router.get("/assessments/{assessment_id}/results/{version}/export/{kind}")
def download_export(
    assessment_id: str,
    version: int,
    kind: str,
    db: Session = Depends(get_db_session),
):
    if kind not in {"pdf", "json"}:
        from app.core.errors import AppError

        raise AppError(
            code="invalid_export_kind", message="Export kind must be pdf or json", status_code=400
        )
    path = PublicationService(db).export_path(assessment_id, version, kind)
    filename = sanitize_download_name(f"{assessment_id}-v{version}.{kind}")
    media = "application/pdf" if kind == "pdf" else "application/json"

    def iterator():
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        iterator(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
