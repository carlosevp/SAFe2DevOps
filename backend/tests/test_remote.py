from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models import AuditEvent, InterviewTurn, RemoteContribution, RemoteInvite
from app.models.enums import InterviewTurnSource, RemoteContributionStatus


SAMPLE_ANSWER = (
    "We require one approval before merge and the build pipeline must pass. "
    "Developers open pull requests from short-lived branches and review within a day."
)


def _prepare_assessment(client: TestClient) -> str:
    created = client.post(
        "/api/assessments",
        json={
            "team_name": "Claims Integration",
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
    selection = client.post(
        f"/api/assessments/{assessment_id}/source-selection",
        json={
            "jira_project_key": "CLAIM",
            "jira_project_name": "Claims Integration",
            "ado_project_id": "p1",
            "ado_project_name": "Claims Co",
            "ado_repository_id": "r-api",
            "ado_repository_name": "claims-api",
            "default_branch": "main",
            "selected_pipelines": [{"id": "pl1", "name": "claims-api-CI"}],
        },
    )
    assert selection.status_code == 200, selection.text
    collected = client.post(f"/api/assessments/{assessment_id}/evidence/collect")
    assert collected.status_code == 200, collected.text
    confirmed = client.post(
        f"/api/assessments/{assessment_id}/evidence/{collected.json()['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    started = client.post(f"/api/assessments/{assessment_id}/interview/start")
    assert started.status_code == 200, started.text
    return assessment_id


def _enable_and_invite(client: TestClient, assessment_id: str, ttl_seconds: int | None = None) -> dict:
    enabled = client.put(
        f"/api/assessments/{assessment_id}/remote",
        json={"remote_participation_enabled": True},
    )
    assert enabled.status_code == 200, enabled.text
    body = {}
    if ttl_seconds is not None:
        body["ttl_seconds"] = ttl_seconds
    invite = client.post(f"/api/assessments/{assessment_id}/remote/invites", json=body)
    assert invite.status_code == 200, invite.text
    return invite.json()


def _invite_token(invite: dict) -> str:
    parsed = urlparse(invite["invite_url"])
    qs = parse_qs(parsed.query)
    assert "invite" in qs
    return qs["invite"][0]


def test_invite_creation_and_copy_url(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    invite = _enable_and_invite(client, assessment_id)
    assert invite["jti"]
    assert invite["invite_url"].startswith("http")
    assert "invite=" in invite["invite_url"]
    assert invite["revoked"] is False

    settings = client.get(f"/api/assessments/{assessment_id}/remote")
    assert settings.status_code == 200
    assert settings.json()["remote_participation_enabled"] is True
    assert settings.json()["active_invite"]["jti"] == invite["jti"]
    assert settings.json()["active_invite"]["invite_url"]


def test_invite_expiry(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    invite = _enable_and_invite(client, assessment_id, ttl_seconds=300)
    token = _invite_token(invite)

    db = get_session_factory()()
    try:
        row = db.scalar(select(RemoteInvite).where(RemoteInvite.jti == invite["jti"]))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        db.commit()
    finally:
        db.close()

    topic = client.get("/api/remote/topic", params={"token": token})
    assert topic.status_code == 401
    assert topic.json()["error"]["code"] == "token_expired"


def test_invite_revocation(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    invite = _enable_and_invite(client, assessment_id)
    token = _invite_token(invite)

    revoked = client.post(f"/api/assessments/{assessment_id}/remote/invites/{invite['jti']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True

    topic = client.get("/api/remote/topic", params={"token": token})
    assert topic.status_code == 401
    assert topic.json()["error"]["code"] == "token_revoked"


def test_cross_assessment_isolation(client: TestClient) -> None:
    a1 = _prepare_assessment(client)
    a2 = _prepare_assessment(client)
    invite1 = _enable_and_invite(client, a1)
    token1 = _invite_token(invite1)

    # Contributor joins assessment 1
    joined = client.post(
        "/api/remote/join",
        json={"token": token1, "display_name": "Priya Sharma", "email": "priya@example.com"},
    )
    assert joined.status_code == 200, joined.text
    contributor_id = joined.json()["contributor_id"]

    submitted = client.post(
        "/api/remote/contributions",
        data={"token": token1, "contributor_id": contributor_id, "body": SAMPLE_ANSWER},
    )
    assert submitted.status_code == 200, submitted.text
    contribution_id = submitted.json()["id"]

    # Host of assessment 2 cannot see or dispose assessment 1 contributions
    foreign_list = client.get(f"/api/assessments/{a2}/remote/contributions")
    assert foreign_list.status_code == 200
    assert foreign_list.json()["items"] == []

    foreign_get = client.get(f"/api/assessments/{a2}/remote/contributions/{contribution_id}")
    assert foreign_get.status_code == 404

    foreign_dispose = client.post(
        f"/api/assessments/{a2}/remote/contributions/{contribution_id}/disposition",
        json={"action": "include"},
    )
    assert foreign_dispose.status_code == 404


def test_contribution_submission_and_confirmation(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    invite = _enable_and_invite(client, assessment_id)
    token = _invite_token(invite)

    topic = client.get("/api/remote/topic", params={"token": token})
    assert topic.status_code == 200
    payload = topic.json()
    assert payload["team_name"] == "Claims Integration"
    assert payload["assessment_name"] == "Claims API"
    assert payload["question_text"]
    dumped = json.dumps(payload).lower()
    assert "candidate_score" not in dumped
    assert "ai_score" not in dumped
    assert "admin_final" not in dumped

    joined = client.post(
        "/api/remote/join",
        json={"token": token, "display_name": "Priya Sharma", "email": "priya@example.com"},
    )
    assert joined.status_code == 200
    contributor_id = joined.json()["contributor_id"]

    submitted = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": SAMPLE_ANSWER},
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["status"] == "pending"
    assert "host to review" in body["confirmation_message"].lower()

    inbox = client.get(f"/api/assessments/{assessment_id}/remote/contributions?status=pending")
    assert inbox.status_code == 200
    assert inbox.json()["pending_count"] == 1
    item = inbox.json()["items"][0]
    assert item["contributor_name"] == "Priya Sharma"
    assert item["topic"]
    assert item["preview"]
    assert item["has_attachment"] is False


def test_host_disposition_include_updates_coverage_without_advancing(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    before = client.get(f"/api/assessments/{assessment_id}/interview").json()
    host_question = before["current_question"]

    invite = _enable_and_invite(client, assessment_id)
    token = _invite_token(invite)
    joined = client.post(
        "/api/remote/join",
        json={"token": token, "display_name": "Tom Okeke", "email": "tom@example.com"},
    )
    contributor_id = joined.json()["contributor_id"]
    submitted = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": SAMPLE_ANSWER},
    )
    contribution_id = submitted.json()["id"]

    disposed = client.post(
        f"/api/assessments/{assessment_id}/remote/contributions/{contribution_id}/disposition",
        json={"action": "include"},
    )
    assert disposed.status_code == 200, disposed.text
    result = disposed.json()
    assert result["contribution"]["status"] == "included"
    assert result["host_question_unchanged"] is True
    assert result["notification"]
    assert "Practices affected" in result["notification"] or result["affected_practices"] is not None

    after = client.get(f"/api/assessments/{assessment_id}/interview").json()
    assert after["current_question"] == host_question
    assert after["pending_clarification"] == before.get("pending_clarification")

    db = get_session_factory()()
    try:
        turn = db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.assessment_id == assessment_id,
                InterviewTurn.source == InterviewTurnSource.REMOTE_CONTRIBUTION.value,
            )
        )
        assert turn is not None
        assert turn.answer_text == SAMPLE_ANSWER

        contrib = db.get(RemoteContribution, contribution_id)
        assert contrib is not None
        assert contrib.status == RemoteContributionStatus.INCLUDED.value
        assert contrib.interview_turn_id == turn.id

        audits = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.assessment_id == assessment_id,
                    AuditEvent.event_type == "remote.contribution_disposition",
                )
            )
        )
        assert audits
    finally:
        db.close()


def test_defer_and_dismiss_audited(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    invite = _enable_and_invite(client, assessment_id)
    token = _invite_token(invite)
    joined = client.post(
        "/api/remote/join",
        json={"token": token, "display_name": "Ava Chen", "email": "ava@example.com"},
    )
    contributor_id = joined.json()["contributor_id"]

    first = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": "First note about delivery."},
    )
    second = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": "Second note about quality gates."},
    )
    deferred = client.post(
        f"/api/assessments/{assessment_id}/remote/contributions/{first.json()['id']}/disposition",
        json={"action": "defer"},
    )
    dismissed = client.post(
        f"/api/assessments/{assessment_id}/remote/contributions/{second.json()['id']}/disposition",
        json={"action": "dismiss"},
    )
    assert deferred.status_code == 200
    assert deferred.json()["contribution"]["status"] == "deferred"
    assert dismissed.status_code == 200
    assert dismissed.json()["contribution"]["status"] == "dismissed"


def test_attachment_security(client: TestClient, tmp_data_dir: Path) -> None:
    assessment_id = _prepare_assessment(client)
    invite = _enable_and_invite(client, assessment_id)
    token = _invite_token(invite)
    joined = client.post(
        "/api/remote/join",
        json={"token": token, "display_name": "Sam Lee", "email": "sam@example.com"},
    )
    contributor_id = joined.json()["contributor_id"]

    # Reject executable / unsafe type
    bad = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": "See attached malware."},
        files={"attachment": ("evil.exe", b"MZ\x90\x00not-safe", "application/octet-stream")},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "attachment_type_rejected"

    # Reject path traversal style names with wrong type still blocked by type
    traversal = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": "See attached."},
        files={"attachment": ("../../etc/passwd", b"root:x", "text/plain")},
    )
    # Sanitized name should succeed for text/plain, but never escape upload root
    assert traversal.status_code == 200, traversal.text
    contrib_id = traversal.json()["id"]
    db = get_session_factory()()
    try:
        row = db.get(RemoteContribution, contrib_id)
        assert row is not None
        assert row.attachment_storage_path is not None
        assert ".." not in row.attachment_storage_path
        stored = tmp_data_dir / row.attachment_storage_path
        assert stored.exists()
        assert stored.resolve().is_relative_to((tmp_data_dir).resolve())
    finally:
        db.close()

    # Accept safe PDF
    pdf_ok = client.post(
        "/api/remote/contributions",
        data={"token": token, "contributor_id": contributor_id, "body": "PDF attached."},
        files={"attachment": ("notes.pdf", b"%PDF-1.4\n%safe", "application/pdf")},
    )
    assert pdf_ok.status_code == 200
    assert pdf_ok.json()["has_attachment"] is True


def test_csrf_origin_rejected_for_cookie_mutating_calls(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    # First enable without hostile origin (TestClient default)
    enabled = client.put(
        f"/api/assessments/{assessment_id}/remote",
        json={"remote_participation_enabled": True},
    )
    assert enabled.status_code == 200

    # Simulate browser cookie session + hostile Origin
    client.cookies.set("sd_admin_session", "not-a-real-session-but-present")
    hostile = client.put(
        f"/api/assessments/{assessment_id}/remote",
        json={"remote_participation_enabled": False},
        headers={"Origin": "https://evil.example"},
    )
    assert hostile.status_code == 403
    assert hostile.json()["error"]["code"] == "csrf_origin_rejected"
