from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.db import get_session_factory
from app.models import Assessment
from app.models.enums import AssessmentStatus, CoverageState
from app.services.lifecycle import LifecycleService


def test_required_mock_workflow(client: TestClient) -> None:
    assert client.get("/api/health/ready").status_code == 200

    assert (
        client.put(
            "/api/integrations/jira",
            json={
                "site_url": "https://claimsco.atlassian.net",
                "service_account_email": "svc@claimsco.example",
                "api_token": "demo-jira-token-not-real",
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/integrations/ado",
            json={"org_url": "https://dev.azure.com/claimsco", "pat": "demo-ado-pat-not-real"},
        ).status_code
        == 200
    )
    assert client.post("/api/integrations/jira/test").status_code == 200
    assert client.post("/api/integrations/ado/test").status_code == 200

    created = client.post(
        "/api/assessments",
        json={
            "team_name": "Claims Integration Team E2E",
            "product_service_name": "Claims API",
            "owner_name": "Jordan Mills",
            "owner_email": "jordan@example.com",
            "lookback_days": 90,
            "evidence_influence_mode": "balanced",
            "participation_mode": "hybrid_remote",
        },
    )
    assert created.status_code == 200, created.text
    assessment_id = created.json()["id"]

    assert (
        client.post(
            f"/api/assessments/{assessment_id}/source-selection",
            json={
                "jira_project_key": "CLAIM",
                "jira_project_name": "Claims",
                "ado_project_id": "claims",
                "ado_project_name": "Claims",
                "ado_repository_id": "claims-api",
                "ado_repository_name": "claims-api",
                "default_branch": "main",
                "selected_pipelines": [{"name": "claims-api-CI", "runs": 61}],
            },
        ).status_code
        == 200
    )
    collected = client.post(f"/api/assessments/{assessment_id}/evidence/collect")
    assert collected.status_code == 200
    snapshot_id = collected.json()["id"]
    assert (
        client.post(f"/api/assessments/{assessment_id}/evidence/{snapshot_id}/confirm").status_code
        == 200
    )
    assert client.post(f"/api/assessments/{assessment_id}/interview/start").status_code == 200

    for key, answer in (
        (
            "wf-turn-broad-01",
            "We pick a CLAIM story, branch from main, open a PR, wait for CI, deploy via claims-api-CD-prod.",
        ),
        (
            "wf-turn-clarify-02",
            "CI failures are fixed before merge; E2E is not required on every PR yet.",
        ),
        (
            "wf-turn-voice-03",
            "We watch error rate after deploy and page on-call on spikes.",
        ),
    ):
        turn = client.post(
            f"/api/assessments/{assessment_id}/interview/turns",
            json={"answer_text": answer, "idempotency_key": key},
        )
        assert turn.status_code == 200, turn.text

    assert (
        client.put(
            f"/api/assessments/{assessment_id}/remote",
            json={"remote_participation_enabled": True},
        ).status_code
        == 200
    )
    invite = client.post(f"/api/assessments/{assessment_id}/remote/invites", json={"label": "wf"})
    assert invite.status_code == 200, invite.text
    token = parse_qs(urlparse(invite.json()["invite_url"]).query)["invite"][0]
    joined = client.post(
        "/api/remote/join",
        json={"token": token, "display_name": "Avery Chen", "email": "avery@example.com"},
    )
    assert joined.status_code == 200, joined.text
    contributor_id = joined.json()["contributor_id"]
    contrib = client.post(
        "/api/remote/contributions",
        data={
            "token": token,
            "contributor_id": contributor_id,
            "body": "Synthetic claim-submit check runs after each production deploy.",
        },
    )
    assert contrib.status_code == 200, contrib.text
    assert (
        client.post(
            f"/api/assessments/{assessment_id}/remote/contributions/{contrib.json()['id']}/disposition",
            json={"action": "include"},
        ).status_code
        == 200
    )

    db = get_session_factory()()
    try:
        assessment = db.get(Assessment, assessment_id)
        assert assessment is not None
        for coverage in assessment.practice_coverages:
            coverage.coverage_state = CoverageState.SUFFICIENT.value
            coverage.confidence = 0.8
        LifecycleService(db).transition(
            assessment, AssessmentStatus.INTERVIEW_COMPLETE, actor_subject="admin"
        )
        db.commit()
    finally:
        db.close()

    assert client.post(f"/api/assessments/{assessment_id}/review/start").status_code == 200
    assert client.post(f"/api/assessments/{assessment_id}/review/regenerate").status_code == 200
    assert (
        client.put(
            f"/api/assessments/{assessment_id}/review/practices/test_end_to_end/score",
            json={"score": 1.5, "accept_candidate": False, "rationale": "E2E optional on PRs."},
        ).status_code
        == 200
    )
    pkg = client.get(f"/api/assessments/{assessment_id}/review")
    assert pkg.status_code == 200
    actions = pkg.json().get("improvement_actions") or []
    if actions:
        edited = client.put(
            f"/api/assessments/{assessment_id}/review/improvements/{actions[0]['id']}",
            json={"recommended_action": "Require smoke E2E on PRs."},
        )
        assert edited.status_code == 200
    assert client.post(f"/api/assessments/{assessment_id}/review/approve").status_code == 200
    published = client.post(f"/api/assessments/{assessment_id}/publish")
    assert published.status_code == 200, published.text
    version = published.json()["version"]
    results = client.get(f"/api/assessments/{assessment_id}/results")
    assert results.status_code == 200
    body = results.json()
    assert body.get("radar") or body.get("heatmap") or body.get("overall_maturity") is not None
    assert (
        client.get(f"/api/assessments/{assessment_id}/results/{version}/export/pdf").status_code
        == 200
    )
    assert (
        client.get(f"/api/assessments/{assessment_id}/results/{version}/export/json").status_code
        == 200
    )
