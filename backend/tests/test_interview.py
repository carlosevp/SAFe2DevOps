from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.models.enums import CoverageState
from app.openai.mock import MockInterviewProvider
from app.schemas.interview import InterviewAnalysisAI, PracticeUpdateAI
from app.services.interview import InterviewService


SAMPLE_ANSWER = (
    "We pick up a card from the backlog after planning. Developers work in a feature branch, "
    "raise a pull request, and a pipeline runs unit tests on every PR. After merge to main the "
    "CI build kicks off and deploys to staging. Production deploy is manual. We check acceptance "
    "criteria, then watch dashboards for about twenty minutes after release."
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
    return assessment_id


def test_opening_question_uses_context(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    started = client.post(f"/api/assessments/{assessment_id}/interview/start")
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    q = session["current_question"].lower()
    assert "claims integration" in q
    assert "claims api" in q
    assert "claim" in q
    assert "claims-api" in q
    assert "90" in q
    assert "question" not in json.dumps(session).lower() or "of 16" not in session["current_question"]
    assert "of 16" not in session["current_question"]
    assert session.get("practices")
    dumped = json.dumps(session)
    assert "ai_candidate_score" not in dumped
    assert "candidate_score" not in dumped
    assert "admin_final_score" not in dumped


def test_structured_output_parsing_and_unknown_practice_rejection() -> None:
    from app.assessment_config import get_assessment_model_config
    from app.openai.mock import PRACTICE_KEYWORDS

    provider = MockInterviewProvider()
    analysis, _ = provider.analyze_answer(
        {
            "answer_text": SAMPLE_ANSWER,
            "known_practice_keys": list(PRACTICE_KEYWORDS.keys()),
            "coverage_states": {},
            "influence_mode": "balanced",
        }
    )
    assert isinstance(analysis, InterviewAnalysisAI)
    assert analysis.practice_updates
    assert analysis.next_best_question

    bad = InterviewAnalysisAI(
        response_summary="x",
        claims=[],
        source_attribution=[],
        practice_updates=[
            PracticeUpdateAI(
                practice_key="not_a_real_practice",
                coverage_state=CoverageState.PARTIAL,
                evidence_summary="bad",
                confidence=0.4,
            )
        ],
        evidence_summary="",
        confidence=0.4,
        open_gaps=[],
        contradictions=[],
        needs_immediate_clarification=False,
        clarification_question=None,
        next_best_question="Next?",
        reason_for_next_question="balance",
        completion_recommendation="continue",
        overall_coverage_summary="summary",
    )
    svc = object.__new__(InterviewService)
    svc.model = get_assessment_model_config()
    with pytest.raises(AppError) as exc:
        svc._validate_and_sanitize_analysis(bad)
    assert exc.value.code == "unknown_practice_key"


def test_multi_practice_coverage_and_clarification(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    assert client.post(f"/api/assessments/{assessment_id}/interview/start").status_code == 200

    # Short answer forces clarification.
    short = client.post(
        f"/api/assessments/{assessment_id}/interview/turns",
        json={"answer_text": "We deploy sometimes.", "idempotency_key": "short-turn-1", "is_clarification": False},
    )
    assert short.status_code == 200, short.text
    assert short.json()["session"]["last_outcome"] == "clarify"
    assert short.json()["session"]["pending_clarification"]

    # Rich answer covering multiple practices.
    rich = client.post(
        f"/api/assessments/{assessment_id}/interview/turns",
        json={
            "answer_text": SAMPLE_ANSWER + " Failed quality gates block merging.",
            "idempotency_key": "rich-turn-1",
            "is_clarification": True,
        },
    )
    assert rich.status_code == 200, rich.text
    body = rich.json()
    assert body["covered_practices"] or body["partial_practices"]
    session = body["session"]
    assert "of 16" not in session["current_question"]
    assert session["coverage_confirmation"]


def test_duplicate_submission_idempotent(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    client.post(f"/api/assessments/{assessment_id}/interview/start")
    payload = {
        "answer_text": SAMPLE_ANSWER + " Quality gates block merges when failing.",
        "idempotency_key": "dup-key-12345",
        "is_clarification": False,
    }
    first = client.post(f"/api/assessments/{assessment_id}/interview/turns", json=payload)
    second = client.post(f"/api/assessments/{assessment_id}/interview/turns", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicated"] is True
    assert first.json()["session"]["answered_turn_count"] == second.json()["session"]["answered_turn_count"]


def test_openai_failure_keeps_session_retryable(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    client.post(f"/api/assessments/{assessment_id}/interview/start")

    class Boom:
        name = "mock"

        def analyze_answer(self, context):
            raise AppError(code="openai_request_failed", message="boom", status_code=502)

    with patch("app.services.interview.get_interview_provider", return_value=Boom()):
        failed = client.post(
            f"/api/assessments/{assessment_id}/interview/turns",
            json={
                "answer_text": SAMPLE_ANSWER,
                "idempotency_key": "fail-turn-1",
                "is_clarification": False,
            },
        )
    assert failed.status_code == 502
    # Draft/session still available for retry.
    session = client.get(f"/api/assessments/{assessment_id}/interview")
    assert session.status_code == 200
    assert session.json()["status"] == "interview_active"


def test_score_secrecy_on_workshop_endpoints(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    client.post(f"/api/assessments/{assessment_id}/interview/start")
    client.post(
        f"/api/assessments/{assessment_id}/interview/turns",
        json={
            "answer_text": SAMPLE_ANSWER + " Gates block merges.",
            "idempotency_key": "secret-1",
            "is_clarification": False,
        },
    )
    session = client.get(f"/api/assessments/{assessment_id}/interview").json()
    checkpoint = client.get(f"/api/assessments/{assessment_id}/interview/checkpoint").json()
    for payload in (session, checkpoint):
        text = json.dumps(payload).lower()
        assert "candidate_score" not in text
        assert "ai_candidate_score" not in text
        assert "admin_final_score" not in text
        assert "maturity score" not in text


def test_evidence_modes_affect_contradictions() -> None:
    provider = MockInterviewProvider()
    keys = [
        "develop",
        "build",
        "deploy",
        "verify",
        "monitor",
        "test_end_to_end",
        "stage",
        "hypothesize",
        "collaborate_research",
        "architect",
        "synthesize",
        "respond",
        "release",
        "stabilize",
        "measure",
        "learn",
    ]
    base = {
        "answer_text": SAMPLE_ANSWER + " Delivery is smooth and pipelines almost never fail.",
        "known_practice_keys": keys,
        "coverage_states": {},
        "tool_signals": {"pipeline_success_rate": 50},
    }
    ctx_only, _ = provider.analyze_answer({**base, "influence_mode": "context_only"})
    led, _ = provider.analyze_answer({**base, "influence_mode": "evidence_led"})
    assert not any(u.contradictions for u in ctx_only.practice_updates)
    assert led.contradictions or any(u.contradictions for u in led.practice_updates)


def test_completion_gating_server_side(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    client.post(f"/api/assessments/{assessment_id}/interview/start")
    blocked = client.post(f"/api/assessments/{assessment_id}/interview/complete")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "completion_criteria_unmet"

    # Force coverage via admin coverage endpoint is not available for interview;
    # mutate through DB session factory.
    from app.core.db import get_session_factory
    from app.models import PracticeCoverage
    from sqlalchemy import select

    factory = get_session_factory()
    db = factory()
    try:
        rows = db.scalars(select(PracticeCoverage).where(PracticeCoverage.assessment_id == assessment_id)).all()
        for row in rows:
            row.coverage_state = CoverageState.SUFFICIENT.value
            row.confidence = 0.8
        db.commit()
    finally:
        db.close()

    ok = client.post(f"/api/assessments/{assessment_id}/interview/complete")
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "interview_complete"


def test_autosave_resume_and_checkpoint(client: TestClient) -> None:
    assessment_id = _prepare_assessment(client)
    client.post(f"/api/assessments/{assessment_id}/interview/start")
    draft = client.put(
        f"/api/assessments/{assessment_id}/interview/draft",
        json={"draft_answer_text": "Draft in progress about pipelines and PRs."},
    )
    assert draft.status_code == 200
    assert "Draft in progress" in draft.json()["draft_answer_text"]

    saved = client.post(
        f"/api/assessments/{assessment_id}/interview/save",
        json={"draft_answer_text": "Draft in progress about pipelines and PRs."},
    )
    assert saved.status_code == 200
    assert saved.json()["interview_status"] == "paused"

    resumed = client.post(f"/api/assessments/{assessment_id}/interview/resume")
    assert resumed.status_code == 200
    assert resumed.json()["interview_status"] == "active"
    assert "Draft in progress" in resumed.json()["draft_answer_text"]

    checkpoint = client.get(f"/api/assessments/{assessment_id}/interview/checkpoint")
    assert checkpoint.status_code == 200
    assert "sufficient_count" in checkpoint.json()


def test_ai_settings_update(client: TestClient) -> None:
    current = client.get("/api/ai-settings")
    assert current.status_code == 200
    assert current.json()["assessment_model"]
    updated = client.put(
        "/api/ai-settings",
        json={"assessment_model": "gpt-5.6-terra", "reasoning_effort": "low", "interview_provider": "mock"},
    )
    assert updated.status_code == 200
    assert updated.json()["reasoning_effort"] == "low"


def test_figma_workflow_e2e_text_first(client: TestClient) -> None:
    """End-to-end text-first path matching the Figma workshop flow."""
    assessment_id = _prepare_assessment(client)
    start = client.post(f"/api/assessments/{assessment_id}/interview/start")
    assert start.status_code == 200
    session = start.json()["session"]
    assert session["current_question"]
    assert session["why_asking"]
    assert session["evidence_context"]

    turn = client.post(
        f"/api/assessments/{assessment_id}/interview/turns",
        json={
            "answer_text": SAMPLE_ANSWER,
            "idempotency_key": "e2e-turn-1",
            "is_clarification": False,
        },
    )
    assert turn.status_code == 200
    outcome = turn.json()["session"]["last_outcome"]
    assert outcome in {"clarify", "sufficient"}

    if outcome == "clarify":
        clar = client.post(
            f"/api/assessments/{assessment_id}/interview/turns",
            json={
                "answer_text": "Yes, failed quality gates block merging to main.",
                "idempotency_key": "e2e-turn-2",
                "is_clarification": True,
            },
        )
        assert clar.status_code == 200
        assert clar.json()["session"]["last_outcome"] in {"sufficient", "clarify"}

    cp = client.get(f"/api/assessments/{assessment_id}/interview/checkpoint")
    assert cp.status_code == 200
    assert "of 16 practices" in cp.json()["summary"]

    # Scores remain hidden throughout workshop payloads.
    assert "ai_candidate_score" not in json.dumps(turn.json())
