from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.errors import AppError
from app.models.enums import AssessmentStatus, EvidenceInfluenceMode
from app.services.assessment import AssessmentService
from app.services.lifecycle import LifecycleService
from app.services.publication import PublicationService
from app.services.seed import SeedService


@pytest.fixture()
def db(app_env: dict[str, str]) -> Session:
    # Ensure app migrations ran via create_app lifespan path.
    from app.main import create_app

    with TestClient(create_app()):
        pass
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def test_lifecycle_transitions(db: Session) -> None:
    service = AssessmentService(db)
    assessment = service.create(
        team_name="Team A",
        product_service_name="Service A",
        owner_name="Owner",
        owner_email="owner@example.com",
        lookback_days=60,
        evidence_influence_mode=EvidenceInfluenceMode.CONTEXT_ONLY,
    )
    lifecycle = LifecycleService(db)
    lifecycle.transition(assessment, AssessmentStatus.COLLECTING_EVIDENCE)
    lifecycle.transition(assessment, AssessmentStatus.EVIDENCE_READY)
    lifecycle.transition(assessment, AssessmentStatus.INTERVIEW_ACTIVE)
    lifecycle.transition(assessment, AssessmentStatus.INTERVIEW_COMPLETE)
    lifecycle.transition(assessment, AssessmentStatus.ADMIN_REVIEW)
    assert assessment.status == AssessmentStatus.ADMIN_REVIEW.value

    with pytest.raises(AppError) as exc:
        lifecycle.transition(assessment, AssessmentStatus.SETUP)
    assert exc.value.code == "invalid_lifecycle_transition"


@pytest.mark.parametrize(
    "mode",
    [
        EvidenceInfluenceMode.CONTEXT_ONLY,
        EvidenceInfluenceMode.BALANCED,
        EvidenceInfluenceMode.EVIDENCE_LED,
    ],
)
def test_all_evidence_influence_modes(db: Session, mode: EvidenceInfluenceMode) -> None:
    assessment = AssessmentService(db).create(
        team_name=f"Team {mode.value}",
        product_service_name="Service",
        owner_name="Owner",
        owner_email="owner@example.com",
        evidence_influence_mode=mode,
    )
    assert assessment.evidence_influence_mode == mode.value


def test_lookback_limits(db: Session) -> None:
    service = AssessmentService(db)
    with pytest.raises(AppError) as low:
        service.create(
            team_name="Too Short",
            product_service_name="Service",
            owner_name="Owner",
            owner_email="owner@example.com",
            lookback_days=29,
        )
    assert low.value.code == "invalid_lookback_days"

    with pytest.raises(AppError) as high:
        service.create(
            team_name="Too Long",
            product_service_name="Service",
            owner_name="Owner",
            owner_email="owner@example.com",
            lookback_days=366,
        )
    assert high.value.code == "invalid_lookback_days"


def test_score_secrecy_and_rationale(client: TestClient, admin_password: str, db: Session) -> None:
    seed = SeedService(db).seed_demo()
    db.commit()

    participant = client.get(f"/api/assessments/{seed.id}/coverage/participant")
    assert participant.status_code == 200
    body = participant.json()
    assert body
    assert all("ai_candidate_score" not in row for row in body)
    dumped = json.dumps(body)
    assert "ai_candidate_score" not in dumped

    login = client.post("/api/auth/admin/login", json={"password": admin_password})
    assert login.status_code == 200

    admin = client.get(f"/api/assessments/{seed.id}/coverage/admin")
    assert admin.status_code == 200
    assert any(row.get("ai_candidate_score") is not None for row in admin.json())

    no_rationale = client.put(
        f"/api/assessments/{seed.id}/coverage/develop/admin-score",
        json={"score": 2.0},
    )
    assert no_rationale.status_code == 400
    assert no_rationale.json()["error"]["code"] == "rationale_required"

    ok = client.put(
        f"/api/assessments/{seed.id}/coverage/develop/admin-score",
        json={"score": 2.0, "rationale": "Pipeline evidence shows weaker automation than conversation implied."},
    )
    assert ok.status_code == 200
    assert ok.json()["admin_final_score"] == 2.0


def test_published_version_immutability(db: Session) -> None:
    from app.services.review import ReviewService

    assessment = SeedService(db).seed_demo()
    # Ensure every practice has a score for publication.
    for coverage in assessment.practice_coverages:
        if coverage.ai_candidate_score is None:
            coverage.ai_candidate_score = 2.0
            coverage.admin_final_score = 2.0
            coverage.admin_rationale = "Seeded for publish"
        elif coverage.admin_final_score is None:
            coverage.admin_final_score = coverage.ai_candidate_score
    db.flush()

    ReviewService(db).approve(assessment.id, actor="admin")
    db.flush()

    pub = PublicationService(db)
    report = pub.publish(assessment.id, published_by="admin")
    assert report.version == 1
    assert report.immutable is True
    assert assessment.status == AssessmentStatus.PUBLISHED.value
    assert report.export_json_relpath
    assert report.export_pdf_relpath

    with pytest.raises(AppError) as exc:
        pub.update_report(report.id, title="mutated")
    assert exc.value.code == "report_immutable"

    scores = json.loads(report.scores_json)
    assert "ai_candidate_score" not in json.dumps(scores)

    # Corrections create a new version via admin_review → publish.
    LifecycleService(db).transition(assessment, AssessmentStatus.ADMIN_REVIEW, actor_subject="admin")
    ReviewService(db).approve(assessment.id, actor="admin")
    report2 = pub.publish(assessment.id, published_by="admin")
    assert report2.version == 2
