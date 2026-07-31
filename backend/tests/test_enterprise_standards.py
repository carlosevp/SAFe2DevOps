from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models import AssessmentStandardSnapshot, EnterpriseStandard
from app.models.enterprise import AssessmentTechnologyContext, EnterpriseStandardCondition
from app.models.enums import (
    ApplicabilityMode,
    ConditionLogicalGroup,
    ConditionOperator,
)
from app.services.enterprise_standards import EnterpriseStandardsService
from app.services.seed import SeedService


def test_standards_crud(client: TestClient) -> None:
    created = client.post(
        "/api/enterprise-standards",
        json={
            "stable_key": "test_secret_vault",
            "title": "Test secret vault",
            "category": "Security",
            "description": "Use approved vault",
            "requirement_level": "required",
            "active": True,
            "applicability_mode": "conditions",
            "mapped_practice_keys": ["develop", "build"],
            "primary_interview_guidance": "Ask about secrets",
            "recommendation_when_unmet": "Adopt Secret Server",
            "display_order": 1,
            "conditions": [
                {
                    "field": "application_has_secrets",
                    "operator": "is_true",
                    "value": "true",
                    "logical_group": "all",
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    standard_id = created.json()["id"]

    listed = client.get("/api/enterprise-standards?search=secret&active=true")
    assert listed.status_code == 200
    assert any(item["stable_key"] == "test_secret_vault" for item in listed.json())

    updated = client.put(
        f"/api/enterprise-standards/{standard_id}",
        json={"title": "Test secret vault (updated)"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"].endswith("(updated)")

    dup = client.post(f"/api/enterprise-standards/{standard_id}/duplicate")
    assert dup.status_code == 200
    assert dup.json()["stable_key"].startswith("test_secret_vault_copy")

    deactivated = client.post(f"/api/enterprise-standards/{standard_id}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False

    exported = client.get("/api/enterprise-standards/export")
    assert exported.status_code == 200
    assert "standards" in exported.json()


def test_import_validation_rejects_bad_fields(client: TestClient) -> None:
    bad = client.post(
        "/api/enterprise-standards/import",
        json={
            "standards": [
                {
                    "stable_key": "bad_std",
                    "title": "Bad",
                    "category": "X",
                    "applicability_mode": "conditions",
                    "mapped_practice_keys": ["develop"],
                    "conditions": [
                        {
                            "field": "not_a_field",
                            "operator": "equals",
                            "value": "x",
                            "logical_group": "all",
                        }
                    ],
                }
            ]
        },
    )
    assert bad.status_code == 422


def test_applicability_rules_snapshots_and_isolation(client: TestClient) -> None:
    db = get_session_factory()()
    try:
        EnterpriseStandardsService(db).seed_library()
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/assessments",
        json={
            "team_name": "Enterprise Overlay Team",
            "product_service_name": "Claims API",
            "owner_name": "Jordan Mills",
            "owner_email": "jordan@example.com",
            "lookback_days": 90,
            "evidence_influence_mode": "balanced",
            "participation_mode": "hybrid_remote",
        },
    )
    assert created.status_code == 200
    assessment_id = created.json()["id"]

    ctx = client.put(
        f"/api/assessments/{assessment_id}/technology-context?confirm=true",
        json={
            "primary_technology": "Java",
            "application_type": "API",
            "current_platform": "WebSphere",
            "target_platform": "OpenShift",
            "hosting_location": "on_premises",
            "customer_exposure": "customer_facing",
            "lifecycle_stage": "modernizing",
            "application_has_secrets": True,
            "uses_cicd": True,
            "context_tags": ["claims"],
            "notes": "demo",
        },
    )
    assert ctx.status_code == 200, ctx.text
    body = ctx.json()
    assert body["applicable_standard_count"] >= 4
    assert "approved_secret_management" in body["applicable_standard_keys"]
    assert "preferred_java_runtime_openshift" in body["applicable_standard_keys"]

    ctx2 = client.put(
        f"/api/assessments/{assessment_id}/technology-context",
        json={
            "primary_technology": "Python",
            "application_type": "API",
            "current_platform": "Linux",
            "target_platform": "Linux",
            "hosting_location": "cloud",
            "customer_exposure": "internal",
            "lifecycle_stage": "current",
            "application_has_secrets": False,
            "uses_cicd": True,
            "context_tags": [],
            "notes": "",
        },
    )
    assert ctx2.status_code == 200
    keys = ctx2.json()["applicable_standard_keys"]
    assert "approved_secret_management" not in keys
    assert "preferred_java_runtime_openshift" not in keys

    client.put(
        f"/api/assessments/{assessment_id}/technology-context?confirm=true",
        json={
            "primary_technology": "Java",
            "application_type": "API",
            "current_platform": "WebSphere",
            "target_platform": "OpenShift",
            "hosting_location": "on_premises",
            "customer_exposure": "customer_facing",
            "lifecycle_stage": "modernizing",
            "application_has_secrets": True,
            "uses_cicd": True,
            "context_tags": [],
            "notes": "",
        },
    )
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
                "selected_pipelines": [{"name": "ci"}],
            },
        ).status_code
        == 200
    )
    collected = client.post(f"/api/assessments/{assessment_id}/evidence/collect")
    assert collected.status_code == 200
    assert (
        client.post(
            f"/api/assessments/{assessment_id}/evidence/{collected.json()['id']}/confirm"
        ).status_code
        == 200
    )
    started = client.post(f"/api/assessments/{assessment_id}/interview/start")
    assert started.status_code == 200, started.text

    snaps = client.get(f"/api/assessments/{assessment_id}/enterprise-standards/snapshots")
    assert snaps.status_code == 200
    snap_keys = {s["stable_key"] for s in snaps.json()}
    assert "approved_secret_management" in snap_keys

    db = get_session_factory()()
    try:
        std = db.scalar(
            select(EnterpriseStandard).where(
                EnterpriseStandard.stable_key == "approved_secret_management"
            )
        )
        assert std is not None
        std.title = "Changed after snapshot"
        db.commit()
        snap_row = db.scalar(
            select(AssessmentStandardSnapshot).where(
                AssessmentStandardSnapshot.assessment_id == assessment_id,
                AssessmentStandardSnapshot.stable_key == "approved_secret_management",
            )
        )
        assert snap_row is not None
        definition = json.loads(snap_row.definition_json)
        assert definition["title"] != "Changed after snapshot"
    finally:
        db.close()

    # Combined interview turn should accept known standard updates
    turn = client.post(
        f"/api/assessments/{assessment_id}/interview/turns",
        json={
            "answer_text": (
                "We open pull requests with required quality gates, deploy through the approved pipeline, "
                "and retrieve credentials from Secret Server rather than hardcoding tokens."
            ),
            "idempotency_key": "enterprise-turn-0001",
        },
    )
    assert turn.status_code == 200, turn.text


def test_findings_admin_adjust_and_publish(client: TestClient) -> None:
    db = get_session_factory()()
    try:
        assessment = SeedService(db).seed_demo(publish=False)
        db.commit()
        assessment_id = assessment.id
    finally:
        db.close()

    findings = client.get(f"/api/assessments/{assessment_id}/review/enterprise-standards")
    assert findings.status_code == 200
    assert findings.json()
    assert "enterprise_alignment_score" not in json.dumps(findings.json())

    finding_id = findings.json()[0]["id"]
    adjusted = client.put(
        f"/api/assessments/{assessment_id}/review/enterprise-standards/{finding_id}",
        json={
            "status": "finding",
            "observation": "Admin observation",
            "recommendation": "Do the approved thing",
            "admin_note": "Noted",
        },
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["admin_edited_status"] is True

    assert client.post(f"/api/assessments/{assessment_id}/review/start").status_code in {200, 409}
    regen = client.post(f"/api/assessments/{assessment_id}/review/regenerate")
    assert regen.status_code in {200, 409}
    approve = client.post(f"/api/assessments/{assessment_id}/review/approve")
    assert approve.status_code == 200, approve.text
    published = client.post(f"/api/assessments/{assessment_id}/publish")
    assert published.status_code == 200, published.text
    results = client.get(f"/api/assessments/{assessment_id}/results")
    assert results.status_code == 200
    body = results.json()
    assert body.get("enterprise_standards")
    assert body["enterprise_standards"]["applicable_count"] >= 1
    assert "enterprise_alignment_score" not in json.dumps(body)
    assert "ai_candidate_score" not in json.dumps(body)
    # Distinct report sections: SAFe score remains independent; plan carries refs.
    assert isinstance(body["overall_maturity"], (int, float))
    assert body["improvement_actions"]
    assert any(
        item.get("related_practice_keys") is not None
        and item.get("related_standard_keys") is not None
        for item in body["improvement_actions"]
    )
    # Enterprise-only or merged actions should preserve standard references when present.
    with_standards = [
        item for item in body["improvement_actions"] if item.get("related_standard_keys")
    ]
    assert with_standards
    assert all("sources" in item for item in body["improvement_actions"])


def test_all_any_condition_behavior() -> None:
    standard = EnterpriseStandard(
        stable_key="combo",
        title="Combo",
        category="X",
        applicability_mode=ApplicabilityMode.CONDITIONS.value,
        mapped_practice_keys_json="[]",
    )
    standard.conditions = [
        EnterpriseStandardCondition(
            field="primary_technology",
            operator=ConditionOperator.EQUALS.value,
            value="Java",
            logical_group=ConditionLogicalGroup.ALL.value,
        ),
        EnterpriseStandardCondition(
            field="custom_context_tag",
            operator=ConditionOperator.EQUALS.value,
            value="claims",
            logical_group=ConditionLogicalGroup.ANY.value,
        ),
        EnterpriseStandardCondition(
            field="custom_context_tag",
            operator=ConditionOperator.EQUALS.value,
            value="billing",
            logical_group=ConditionLogicalGroup.ANY.value,
        ),
    ]
    ctx = AssessmentTechnologyContext(
        assessment_id="x",
        primary_technology="Java",
        context_tags_json=json.dumps(["claims"]),
        application_has_secrets=True,
        uses_cicd=True,
    )
    service = EnterpriseStandardsService.__new__(EnterpriseStandardsService)
    assert service.is_applicable(standard, ctx) is True
    ctx.context_tags_json = json.dumps(["other"])
    assert service.is_applicable(standard, ctx) is False
    ctx.primary_technology = "Python"
    ctx.context_tags_json = json.dumps(["claims"])
    assert service.is_applicable(standard, ctx) is False


def test_unknown_standard_key_rejected(client: TestClient) -> None:
    db = get_session_factory()()
    try:
        EnterpriseStandardsService(db).seed_library()
        assessment = SeedService(db).seed_demo(publish=False)
        db.commit()
        assessment_id = assessment.id
    finally:
        db.close()

    # Force an interview turn with an invented standard via direct service validation path
    from app.schemas.enterprise import StandardUpdateAI
    from app.models.enums import StandardFindingStatus
    from app.core.errors import AppError

    db = get_session_factory()()
    try:
        service = EnterpriseStandardsService(db)
        try:
            service.apply_standard_updates_from_analysis(
                assessment_id,
                [
                    StandardUpdateAI(
                        standard_key="invented_standard",
                        status=StandardFindingStatus.ALIGNED,
                        evidence_summary="nope",
                        confidence=0.9,
                    )
                ],
            )
            raised = False
        except AppError as exc:
            raised = True
            assert exc.code == "unknown_standard_key"
        assert raised
    finally:
        db.close()


def test_recommendation_dedupe_and_no_enterprise_score() -> None:
    from app.services.publication import _norm_rec, build_consolidated_improvement_plan

    assert _norm_rec("The team should adopt Secret Server") == _norm_rec("Adopt Secret Server")
    assert "enterprise_alignment_score" not in _norm_rec("aligned findings")

    plan = build_consolidated_improvement_plan(
        [
            {
                "id": "safe-1",
                "title": "Require Secret Server for pipeline secrets",
                "practice_key": "build",
                "domain_key": "continuous_integration",
                "observation": "Tokens still appear in variable groups.",
                "supporting_evidence": "Interview + ADO variables",
                "why_it_matters": "Credential leakage risk",
                "recommended_action": "Require Secret Server retrieval for pipeline secrets",
                "time_horizon": "next_sprint",
                "kpi": "Secrets retrieved from vault",
                "priority": 2,
            }
        ],
        [
            {
                "stable_key": "approved_secret_management",
                "standard": "Approved secret management",
                "requirement_level": "required",
                "observation": "Builds still reference pipeline variables for some API tokens.",
                "supporting_evidence": "Demo admin adjustment",
                "recommendation": (
                    "Require Secret Server retrieval for runtime and pipeline secrets; "
                    "remove hardcoded credentials from repositories."
                ),
                "related_safe_practices": ["develop", "build", "deploy"],
                "suggested_time_horizon": "next_sprint",
            },
            {
                "stable_key": "approved_production_observability",
                "standard": "Approved production observability",
                "requirement_level": "required",
                "observation": "Logging onboarding incomplete.",
                "supporting_evidence": "Interview",
                "recommendation": "Onboard the service to approved monitoring and logging platforms.",
                "related_safe_practices": ["monitor", "respond", "stabilize"],
                "suggested_time_horizon": "next_sprint",
            },
        ],
    )
    assert len(plan) == 2
    merged = next(item for item in plan if item["id"] == "safe-1")
    assert "enterprise" in merged["sources"]
    assert "approved_secret_management" in merged["related_standard_keys"]
    assert "Approved secret management" in merged["related_standard_titles"]
    assert set(merged["related_practice_keys"]) >= {"build", "develop", "deploy"}
    observability = next(item for item in plan if "observability" in item["id"])
    assert observability["sources"] == ["enterprise"]
    assert "monitor" in observability["related_practice_keys"]


def test_multi_coverage_question_hides_enterprise_status(client: TestClient) -> None:
    db = get_session_factory()()
    try:
        assessment = SeedService(db).seed_demo(publish=False)
        # Leave mapped practices open so multi-coverage selection can fire.
        for coverage in assessment.practice_coverages:
            if coverage.practice_key in {"develop", "build", "deploy", "test_end_to_end"}:
                coverage.coverage_state = "not_discussed"
        db.commit()
        assessment_id = assessment.id
        from app.models.enums import StandardFindingStatus
        from app.schemas.enterprise import StandardUpdateAI
        from app.schemas.interview import InterviewAnalysisAI
        from app.services.interview import InterviewService

        service = InterviewService(db)
        analysis = InterviewAnalysisAI(
            response_summary="partial answer",
            practice_updates=[],
            standard_updates=[
                StandardUpdateAI(
                    standard_key="approved_secret_management",
                    status=StandardFindingStatus.PARTIALLY_ALIGNED,
                    evidence_summary="Mentioned vault usage",
                    confidence=0.6,
                )
            ],
            confidence=0.5,
            open_gaps=["missing secret management detail"],
            contradictions=[],
            needs_immediate_clarification=False,
            clarification_question=None,
            next_best_question=(
                "Walk us through what checks must pass before merge and how credentials "
                "are provided to builds and deployments."
            ),
            reason_for_next_question="Need more coverage of build and secret management.",
            overall_coverage_summary="partial",
        )
        question = service._select_multi_coverage_question(assessment, analysis)
        assert question is not None
        lowered = (question["question"] + " " + question["why"]).lower()
        assert "enterprise standard" not in lowered
        assert "partially_aligned" not in lowered
        assert "standard finding" not in lowered
        confirmation = service._coverage_confirmation(analysis)
        assert "useful context" in confirmation.lower()
        assert "enterprise standard" not in confirmation.lower()
        assert "partially_aligned" not in confirmation.lower()
        assert "aligned" not in confirmation.lower()
        payload = service.enterprise.interview_context_payload(assessment_id)
        assert payload["known_standard_keys"]
    finally:
        db.close()


def test_cannot_delete_referenced_standard(client: TestClient) -> None:
    db = get_session_factory()()
    try:
        SeedService(db).seed_demo(publish=False)
        db.commit()
        std = db.scalar(
            select(EnterpriseStandard).where(
                EnterpriseStandard.stable_key == "approved_secret_management"
            )
        )
        assert std is not None
        standard_id = std.id
    finally:
        db.close()

    deleted = client.delete(f"/api/enterprise-standards/{standard_id}")
    assert deleted.status_code == 409
