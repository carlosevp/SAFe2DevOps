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
    RemoteContribution,
    RemoteContributor,
)
from app.models.enums import (
    AssessmentStatus,
    ConnectionStatus,
    CoverageState,
    EvidenceInfluenceMode,
    InterviewTurnSource,
    InterviewTurnType,
    ParticipationMode,
    RemoteContributionStatus,
)
from app.models.review import AssessmentReview
from app.repositories.integration import IntegrationRepository
from app.services.assessment import AssessmentService
from app.services.publication import PublicationService
from app.services.review import ReviewService


class SeedService:
    """Deterministic demo/seed data for local development and tests."""

    DEMO_TEAM = "Claims Integration Team"
    DEMO_ASSESSMENT_KEY = "demo-claims-integration"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentService(db)
        self.integrations = IntegrationRepository(db)
        self.model = get_assessment_model_config()

    def seed_demo(self, *, publish: bool = False) -> Assessment:
        integration = self.integrations.get_or_create_singleton()
        self._seed_integration(integration)

        existing = self.db.scalar(select(Assessment).where(Assessment.team_name == self.DEMO_TEAM))
        if existing is None:
            # Backward-compatible lookup for earlier seed name.
            existing = self.db.scalar(
                select(Assessment).where(Assessment.team_name == "Claims Integration")
            )
        if existing is not None:
            return existing

        assessment = self.assessments.create(
            team_name=self.DEMO_TEAM,
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
        self._seed_remote_contribution(assessment)
        self._seed_coverage_scores(assessment)
        self._seed_improvements(assessment)
        self._seed_admin_adjustment(assessment)
        assessment.status = AssessmentStatus.ADMIN_REVIEW.value
        self.db.flush()

        if publish:
            self._seed_review_and_publish(assessment)

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
            ("ado_deployment_frequency", "Production deploys / 90d", "31", 31.0, "azdo"),
            ("jira_wip", "Average WIP", "9", 9.0, "jira"),
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
        turns = [
            InterviewTurn(
                assessment_id=assessment.id,
                sequence=1,
                turn_type=InterviewTurnType.BROAD.value,
                source=InterviewTurnSource.ROOM_TYPED.value,
                question_text="Walk us through a recent representative change from need to production.",
                answer_text=(
                    "We pull a CLAIM story, refine acceptance criteria with product, branch from main, "
                    "open a PR on claims-api, wait for CI, then deploy via claims-api-CD-prod."
                ),
                practice_keys_json=json.dumps(["develop", "build", "deploy"]),
                structured_analysis_ref="analysis/demo/turn-1",
                idempotency_key="demo-turn-1",
                content_trust="untrusted",
            ),
            InterviewTurn(
                assessment_id=assessment.id,
                sequence=2,
                turn_type=InterviewTurnType.CLARIFICATION.value,
                source=InterviewTurnSource.ROOM_TYPED.value,
                question_text="When CI fails on that PR, what happens next before anyone merges?",
                answer_text=(
                    "The author fixes the build locally, pushes again, and we only merge after green checks. "
                    "We do not have a required E2E suite on every PR yet."
                ),
                practice_keys_json=json.dumps(["build", "test_end_to_end"]),
                structured_analysis_ref="analysis/demo/turn-2",
                idempotency_key="demo-turn-2",
                content_trust="untrusted",
            ),
            InterviewTurn(
                assessment_id=assessment.id,
                sequence=3,
                turn_type=InterviewTurnType.BROAD.value,
                source=InterviewTurnSource.ROOM_VOICE.value,
                question_text="How do you know a production deploy is healthy after release?",
                answer_text=(
                    "We watch dashboards for error rate and latency for about fifteen minutes, "
                    "and on-call gets paged if the claims submit path spikes."
                ),
                practice_keys_json=json.dumps(["verify", "monitor", "respond"]),
                structured_analysis_ref="analysis/demo/turn-3",
                idempotency_key="demo-turn-3",
                content_trust="untrusted",
            ),
        ]
        for turn in turns:
            self.db.add(turn)
        self.db.flush()

    def _seed_remote_contribution(self, assessment: Assessment) -> None:
        contributor = RemoteContributor(
            assessment_id=assessment.id,
            display_name="Avery Chen",
            email="avery.chen@example.com",
            invite_token_jti="demo-remote-jti",
        )
        self.db.add(contributor)
        self.db.flush()
        contribution = RemoteContribution(
            assessment_id=assessment.id,
            contributor_id=contributor.id,
            topic="Continuous Integration",
            question_text="How do you know a production deploy is healthy after release?",
            evidence_context="CLAIMS production monitoring discussion",
            body=(
                "From the platform side: we also require a synthetic claim-submit check after each "
                "claims-api-CD-prod run. If it fails twice, we auto-rollback."
            ),
            status=RemoteContributionStatus.INCLUDED.value,
            content_trust="untrusted",
            disposition_by="mock-host",
            disposition_at=datetime(2026, 7, 16, 14, 5, tzinfo=UTC),
            affected_practices_json=json.dumps(["verify", "respond"]),
            host_notified=True,
        )
        self.db.add(contribution)
        self.db.add(
            InterviewTurn(
                assessment_id=assessment.id,
                sequence=4,
                turn_type=InterviewTurnType.BROAD.value,
                source=InterviewTurnSource.REMOTE_CONTRIBUTION.value,
                question_text=contribution.question_text,
                answer_text=contribution.body,
                practice_keys_json=contribution.affected_practices_json,
                structured_analysis_ref="analysis/demo/remote-1",
                idempotency_key="demo-remote-1",
                content_trust="untrusted",
            )
        )
        self.db.flush()

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
            "monitor": (2.5, CoverageState.PARTIAL),
            "respond": (3.0, CoverageState.SUFFICIENT),
            "release": (2.0, CoverageState.PARTIAL),
            "stabilize": (2.0, CoverageState.PARTIAL),
            "measure": (2.0, CoverageState.PARTIAL),
            "learn": (2.0, CoverageState.PARTIAL),
        }
        for coverage in assessment.practice_coverages:
            score, state = seeded_scores[coverage.practice_key]
            coverage.coverage_state = state.value
            coverage.ai_candidate_score = score
            coverage.confidence = 0.72
            coverage.named_maturity_level = "Emerging" if score < 3 else "Established"
            coverage.evidence_summaries_json = json.dumps(
                ["Interview transcript", "CLAIM Jira metrics", "claims-api ADO pipelines"]
            )

    def _seed_admin_adjustment(self, assessment: Assessment) -> None:
        for coverage in assessment.practice_coverages:
            if coverage.practice_key == "test_end_to_end":
                coverage.admin_final_score = 1.5
                coverage.admin_rationale = "Pipeline evidence shows E2E is optional on PRs; conversation overstated gate strength."
                coverage.named_maturity_level = "Initial"
            if coverage.practice_key == "develop":
                coverage.admin_final_score = coverage.ai_candidate_score

    def _seed_improvements(self, assessment: Assessment) -> None:
        self.db.add(
            ImprovementAction(
                assessment_id=assessment.id,
                practice_key="test_end_to_end",
                domain_key="continuous_integration",
                title="Require smoke E2E on pull requests",
                detail="Make claims-api-PR-validation run a smoke E2E pack before merge.",
                observation="E2E validation is inconsistent across pull requests.",
                supporting_evidence="ADO pipeline success gaps and interview clarification on missing required E2E.",
                why_it_matters="Ungated merges allow known failures to accumulate in main.",
                recommended_action=(
                    "Require claims-api-PR-validation to run a smoke E2E pack before merge "
                    "(edited by admin for demo)."
                ),
                time_horizon="next_sprint",
                kpi="% of PRs completing required E2E checks before merge",
                priority=1,
                owner_hint="QA + platform",
            )
        )
        self.db.add(
            ImprovementAction(
                assessment_id=assessment.id,
                practice_key="monitor",
                domain_key="continuous_deployment",
                title="Codify post-deploy synthetic checks",
                detail="Promote the synthetic claim-submit check to a required release gate.",
                observation="Remote contributor described auto-rollback that is not yet standardized.",
                supporting_evidence="Remote contribution from Avery Chen; production deploy discussion.",
                why_it_matters="Inconsistent verification delays detection of customer-impacting regressions.",
                recommended_action="Document and enforce synthetic claim-submit checks for every production deploy.",
                time_horizon="this_pi",
                kpi="Time-to-detect for claim-submit regressions after deploy",
                priority=2,
                owner_hint="SRE",
            )
        )

    def _seed_review_and_publish(self, assessment: Assessment) -> None:
        review = AssessmentReview(
            assessment_id=assessment.id,
            reviewer_subject="demo-seed",
            overall_maturity=2.6,
            confidence_summary="Moderate confidence from hybrid interview + CLAIM/claims-api evidence.",
            evidence_quality="Representative 90-day lookback with known E2E gaps.",
            strengths_json=json.dumps(
                ["Trunk-based PR flow", "Production deploy pipeline", "On-call response path"]
            ),
            maturity_gaps_json=json.dumps(
                ["Required E2E on PRs", "Consistent post-deploy verification"]
            ),
            limitations_json=json.dumps(["Mock integrations in demo mode", "Single team sample"]),
            notes="Demo published report for Claims Integration Team.",
            ready_to_publish=False,
        )
        self.db.add(review)
        self.db.flush()

        ReviewService(self.db).approve(assessment.id, actor="demo-seed")
        PublicationService(self.db).publish(assessment.id, published_by="demo-seed")
