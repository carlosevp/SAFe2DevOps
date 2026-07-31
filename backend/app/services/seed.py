from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment_config import get_assessment_model_config
from app.core.encryption import encrypt_secret
from app.models import (
    Assessment,
    EvidenceMetric,
    EvidenceSnapshot,
    ImprovementAction,
    IntegrationConfiguration,
    InterviewTurn,
)
from app.models.enums import (
    AssessmentStatus,
    ConnectionStatus,
    CoverageState,
    EvidenceInfluenceMode,
    InterviewTurnSource,
    InterviewTurnType,
    ParticipationMode,
)
from app.repositories.integration import IntegrationRepository
from app.services.assessment import AssessmentService


class SeedService:
    """Deterministic demo/seed data for local development and tests."""

    DEMO_ASSESSMENT_KEY = "demo-claims-integration"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentService(db)
        self.integrations = IntegrationRepository(db)
        self.model = get_assessment_model_config()

    def seed_demo(self) -> Assessment:
        integration = self.integrations.get_or_create_singleton()
        self._seed_integration(integration)

        existing = self.db.scalar(select(Assessment).where(Assessment.team_name == "Claims Integration"))
        if existing is not None:
            return existing

        assessment = self.assessments.create(
            team_name="Claims Integration",
            product_service_name="Claims API",
            description="REST API for insurance claims processing.",
            value_stream="Claims Processing",
            owner_name="Jordan Mills",
            owner_email="jordan.mills@example.com",
            lookback_days=90,
            evidence_influence_mode=EvidenceInfluenceMode.BALANCED,
            participation_mode=ParticipationMode.HYBRID_REMOTE,
        )
        self.db.refresh(assessment)
        self.assessments.set_source_selection(

            assessment.id,
            {
                "jira_project_key": "CLAIM",
                "jira_project_name": "Claims",
                "jira_jql": "project = CLAIM AND created >= -90d",
                "ado_project_id": "claims",
                "ado_project_name": "Claims",
                "ado_repository_id": "claims-api",
                "ado_repository_name": "claims-api",
                "default_branch": "main",
                "selected_pipelines": [
                    {"name": "claims-api-CI", "runs": 61},
                    {"name": "claims-api-CD-prod", "runs": 31},
                ],
            },
        )
        self._seed_evidence(assessment)
        self._seed_interview(assessment)
        self._seed_coverage_scores(assessment)
        self._seed_improvements(assessment)
        assessment.status = AssessmentStatus.ADMIN_REVIEW.value
        self.db.flush()
        return assessment

    def _seed_integration(self, integration: IntegrationConfiguration) -> None:
        integration.jira_site_url = "https://claimsco.atlassian.net"
        integration.jira_service_account_email = "svc-maturity@claimsco.example"
        integration.jira_api_token_encrypted = encrypt_secret("demo-jira-token-not-real")
        integration.jira_status = ConnectionStatus.CONNECTED.value
        integration.jira_last_validated_at = datetime(2026, 7, 1, tzinfo=UTC)
        integration.ado_org_url = "https://dev.azure.com/claimsco"
        integration.ado_pat_encrypted = encrypt_secret("demo-ado-pat-not-real")
        integration.ado_status = ConnectionStatus.CONNECTED.value
        integration.ado_last_validated_at = datetime(2026, 7, 1, tzinfo=UTC)
        self.db.flush()

    def _seed_evidence(self, assessment: Assessment) -> None:
        snapshot = EvidenceSnapshot(
            assessment_id=assessment.id,
            lookback_days=assessment.lookback_days,
            collected_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
            jira_project_key="CLAIM",
            ado_repository_name="claims-api",
            provenance_summary="Normalized demo snapshot for CLAIM / claims-api",
            raw_payload_ref="working/demo/evidence-ref.json",
            is_representative=True,
            confirmed_at=datetime(2026, 7, 15, 12, 30, tzinfo=UTC),
        )
        self.db.add(snapshot)
        self.db.flush()
        metrics = [
            ("jira_completed_items", "Jira items completed", "67", 67.0, "jira"),
            ("jira_cycle_time_days", "Median cycle time", "6.4 days", 6.4, "jira"),
            ("ado_prs_completed", "Pull requests completed", "44", 44.0, "azdo"),
            ("ado_pipeline_success", "Pipeline success rate", "84%", 84.0, "azdo"),
        ]
        for key, label, value_text, value_numeric, source in metrics:
            self.db.add(
                EvidenceMetric(
                    snapshot_id=snapshot.id,
                    key=key,
                    label=label,
                    value_text=value_text,
                    value_numeric=value_numeric,
                    source_system=source,
                    provenance=f"{source}:demo:{key}",
                    freshness_label="seed",
                    trend="up",
                )
            )

    def _seed_interview(self, assessment: Assessment) -> None:
        self.db.add(
            InterviewTurn(
                assessment_id=assessment.id,
                sequence=1,
                turn_type=InterviewTurnType.BROAD.value,
                source=InterviewTurnSource.ROOM_VOICE.value,
                question_text="Walk us through a recent representative change from need to production.",
                answer_text="We pick a CLAIM story, branch from main, open a PR, and deploy via claims-api-CD-prod.",
                practice_keys_json=json.dumps(["develop", "build", "deploy"]),
                structured_analysis_ref="analysis/demo/turn-1",
                idempotency_key="demo-turn-1",
            )
        )

    def _seed_coverage_scores(self, assessment: Assessment) -> None:
        seeded_scores = {
            "hypothesize": (3.0, CoverageState.SUFFICIENT),
            "collaborate_research": (2.0, CoverageState.PARTIAL),
            "architect": (3.0, CoverageState.SUFFICIENT),
            "synthesize": (2.0, CoverageState.PARTIAL),
            "develop": (4.0, CoverageState.SUFFICIENT),
            "build": (3.0, CoverageState.SUFFICIENT),
            "test_end_to_end": (2.0, CoverageState.PARTIAL),
            "stage": (3.0, CoverageState.SUFFICIENT),
            "deploy": (3.0, CoverageState.SUFFICIENT),
            "verify": (3.0, CoverageState.SUFFICIENT),
            "monitor": (None, CoverageState.NOT_DISCUSSED),
            "respond": (None, CoverageState.NOT_DISCUSSED),
            "release": (2.0, CoverageState.PARTIAL),
            "stabilize": (2.0, CoverageState.PARTIAL),
            "measure": (None, CoverageState.NOT_DISCUSSED),
            "learn": (None, CoverageState.NOT_DISCUSSED),
        }
        for coverage in assessment.practice_coverages:
            score, state = seeded_scores[coverage.practice_key]
            coverage.coverage_state = state.value
            coverage.ai_candidate_score = score
            coverage.confidence = 0.7 if score is not None else None
            coverage.evidence_summaries_json = json.dumps(["demo evidence summary"]) if score else "[]"

    def _seed_improvements(self, assessment: Assessment) -> None:
        self.db.add(
            ImprovementAction(
                assessment_id=assessment.id,
                practice_key="test_end_to_end",
                domain_key="continuous_integration",
                title="Add end-to-end regression suite to PR validation",
                detail="Require claims-api-PR-validation to run a smoke E2E pack before merge.",
                observation="E2E validation is inconsistent across pull requests.",
                supporting_evidence="Pipeline success rate and PR check gaps from Azure DevOps.",
                why_it_matters="Ungated merges allow known failures to accumulate in main.",
                recommended_action="Require claims-api-PR-validation to run a smoke E2E pack before merge.",
                time_horizon="next_sprint",
                kpi="% of PRs completing required E2E checks before merge",
                priority=1,
                owner_hint="QA + platform",
            )
        )
