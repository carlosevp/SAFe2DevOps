from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.db import get_session_factory
from app.schemas.detailed_report import DetailedAssessmentReport
from app.schemas.scoring import PublishedResultsOut
from app.services.detailed_report import paraphrase, validate_detailed_report
from app.services.seed import SeedService


def test_paraphrase_redacts_sensitive() -> None:
    text = paraphrase("Alice said CLAIM-123 and wrote to alice@example.com about PR #44")
    assert "CLAIM-123" not in text
    assert "alice@example.com" not in text
    assert "[redacted]" in text


def test_generate_detailed_report_for_demo(client: TestClient) -> None:
    session = get_session_factory()()
    try:
        assessment = SeedService(session).seed_demo(publish=False)
        session.commit()
        assessment_id = assessment.id
    finally:
        session.close()

    generated = client.post(
        f"/api/assessments/{assessment_id}/review/detailed-report/generate",
        json={},
    )
    assert generated.status_code == 200, generated.text
    report = DetailedAssessmentReport.model_validate(generated.json())
    assert len(report.domain_reviews) == 4
    assert len(report.practice_reviews) >= 1
    warnings = validate_detailed_report(
        report, practice_keys={p.practice_key for p in report.practice_reviews}
    )
    assert not any(w.startswith("unknown_practice:") for w in warnings)
    for domain in report.domain_reviews:
        for example in domain.illustrative_examples:
            assert example.kind == "illustrative_example"
            assert "illustrative" in example.text.lower()
    dumped = json.dumps(generated.json())
    assert "alice@example.com" not in dumped.lower()


def test_section_edit_preserved(client: TestClient) -> None:
    session = get_session_factory()()
    try:
        assessment = SeedService(session).seed_demo(publish=False)
        session.commit()
        assessment_id = assessment.id
    finally:
        session.close()

    client.post(f"/api/assessments/{assessment_id}/review/detailed-report/generate", json={})
    draft = client.get(f"/api/assessments/{assessment_id}/review/detailed-report").json()
    narrative = draft["executive_narrative"]
    narrative["narrative"] = "Admin-edited executive narrative for Claims Integration."
    edited = client.put(
        f"/api/assessments/{assessment_id}/review/detailed-report/section",
        json={"section": "executive_narrative", "content": narrative},
    )
    assert edited.status_code == 200, edited.text
    assert "Admin-edited executive narrative" in edited.json()["executive_narrative"]["narrative"]


def test_legacy_results_without_detailed_review() -> None:
    payload = PublishedResultsOut(
        assessment_id="a",
        version=1,
        title="t",
        team_name="t",
        product_service_name="p",
        published_at=datetime.now(UTC),
        lookback_days=90,
        evidence_influence_mode="balanced",
        overall_maturity=2.5,
        confidence_summary="Medium",
        evidence_quality="Adequate",
        practices_assessed=10,
        strengths=[],
        maturity_gaps=[],
        evidence_limitations=[],
        radar=[],
        heatmap=[],
        improvement_actions=[],
        chart_summary="",
        scores={},
        detailed_review=None,
    )
    assert payload.detailed_review is None
