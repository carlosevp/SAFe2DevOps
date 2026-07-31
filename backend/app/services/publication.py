from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.core.errors import AppError
from app.models import Assessment, AssessmentReview, PublishedReport
from app.models.enums import AssessmentStatus
from app.repositories.assessment import AssessmentRepository
from app.repositories.publication import PublicationRepository
from app.schemas.scoring import (
    AdminPublishedComparisonOut,
    DomainRadarPoint,
    HeatmapCell,
    ImprovementActionOut,
    PublishedResultsOut,
)
from app.services.audit import AuditService
from app.services.exports import resolve_export_path, write_json_export, write_pdf_export
from app.services.lifecycle import LifecycleService
from app.services.scoring import ScoringService
from app.services.storage import StorageService


class PublicationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentRepository(db)
        self.publications = PublicationRepository(db)
        self.lifecycle = LifecycleService(db)
        self.audit = AuditService(db)
        self.scoring = ScoringService(db)
        self.storage = StorageService()
        self.model = get_assessment_model_config()

    def publish(self, assessment_id: str, *, published_by: str = "admin") -> PublishedReport:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(code="invalid_state", message="Assessment must be in admin_review to publish", status_code=409)

        review = self.db.scalar(
            select(AssessmentReview)
            .where(AssessmentReview.assessment_id == assessment_id)
            .order_by(AssessmentReview.created_at.desc())
        )
        if review is None or not review.ready_to_publish:
            raise AppError(code="review_not_approved", message="Approve the review package before publishing", status_code=409)

        scores: dict[str, float] = {}
        ai_vs_final: dict[str, dict] = {}
        for coverage in assessment.practice_coverages:
            final = coverage.admin_final_score if coverage.admin_final_score is not None else coverage.ai_candidate_score
            if final is None:
                raise AppError(
                    code="scores_incomplete",
                    message="All practices need a final or candidate score before publication",
                    status_code=400,
                )
            scores[coverage.practice_key] = float(final)
            ai_vs_final[coverage.practice_key] = {
                "ai_candidate_score": coverage.ai_candidate_score,
                "admin_final_score": coverage.admin_final_score if coverage.admin_final_score is not None else float(final),
                "admin_rationale": coverage.admin_rationale,
                "named_maturity_level": coverage.named_maturity_level,
            }

        radar = self.scoring.domain_rollups(assessment, use_final=True)
        heatmap = self.scoring.heatmap(assessment, use_final=True)
        overall = review.overall_maturity if review.overall_maturity is not None else self.scoring.weighted_overall(radar)
        chart_summary = review.notes or (
            f"Overall maturity {overall}/5.0 across four SAFe DevOps domains with "
            f"{sum(1 for s in scores.values() if s >= 2.0)} practices assessed."
        )

        improvement_plan = [
            {
                "id": action.id,
                "title": action.title,
                "practice_key": action.practice_key,
                "domain_key": action.domain_key,
                "observation": action.observation,
                "supporting_evidence": action.supporting_evidence,
                "why_it_matters": action.why_it_matters,
                "recommended_action": action.recommended_action or action.detail,
                "time_horizon": action.time_horizon,
                "kpi": action.kpi,
                "priority": action.priority,
            }
            for action in assessment.improvement_actions
        ]

        version = self.publications.next_version(assessment_id)
        report = PublishedReport(
            assessment_id=assessment_id,
            version=version,
            title=f"{assessment.team_name} · SAFe DevOps Maturity Report",
            summary_markdown=(
                f"Published maturity report for {assessment.product_service_name}. "
                f"Evidence period: {assessment.lookback_days} days. "
                f"Influence mode: {assessment.evidence_influence_mode}."
            ),
            radar_json=json.dumps([p.model_dump() for p in radar]),
            heatmap_json=json.dumps([c.model_dump() for c in heatmap]),
            scores_json=json.dumps(scores),
            improvement_plan_json=json.dumps(improvement_plan),
            published_by=published_by,
            published_at=datetime.now(UTC),
            immutable=True,
            overall_maturity=float(overall),
            confidence_summary=review.confidence_summary or "Medium",
            evidence_quality=review.evidence_quality or "Adequate",
            strengths_json=review.strengths_json,
            maturity_gaps_json=review.maturity_gaps_json,
            limitations_json=review.limitations_json,
            lookback_days=assessment.lookback_days,
            evidence_influence_mode=assessment.evidence_influence_mode,
            prompt_config_version=self.model.version,
            model_name=next((c.scoring_model_version for c in assessment.practice_coverages if c.scoring_model_version), "mock"),
            ai_vs_final_json=json.dumps(ai_vs_final),
            chart_summary=chart_summary,
        )
        self.publications.add(report)
        self.db.flush()

        public_payload = {
            "assessment_id": assessment_id,
            "version": version,
            "title": report.title,
            "team_name": assessment.team_name,
            "product_service_name": assessment.product_service_name,
            "published_at": report.published_at.isoformat(),
            "lookback_days": assessment.lookback_days,
            "evidence_influence_mode": assessment.evidence_influence_mode,
            "overall_maturity": report.overall_maturity,
            "confidence_summary": report.confidence_summary,
            "evidence_quality": report.evidence_quality,
            "strengths": json.loads(report.strengths_json or "[]"),
            "maturity_gaps": json.loads(report.maturity_gaps_json or "[]"),
            "evidence_limitations": json.loads(report.limitations_json or "[]"),
            "radar": [p.model_dump() for p in radar],
            "heatmap": [c.model_dump() for c in heatmap],
            "improvement_actions": improvement_plan,
            "scores": scores,
            "chart_summary": chart_summary,
            "prompt_config_version": report.prompt_config_version,
            "model_name": report.model_name,
        }
        # Public export must never include AI candidate comparison.
        assert "ai_candidate_score" not in json.dumps(public_payload.get("scores"))

        report.export_json_relpath = write_json_export(self.storage, assessment_id, version, public_payload)
        pdf_lines = [
            report.title,
            f"Version {version} · Published {report.published_at.date().isoformat()}",
            f"Overall maturity: {report.overall_maturity}/5.0",
            f"Confidence: {report.confidence_summary}",
            f"Evidence quality: {report.evidence_quality}",
            f"Evidence period: {assessment.lookback_days} days",
            f"Evidence influence mode: {assessment.evidence_influence_mode}",
            "",
            "Strengths:",
            *[f"- {s}" for s in json.loads(report.strengths_json or "[]")[:8]],
            "",
            "Maturity gaps:",
            *[f"- {s}" for s in json.loads(report.maturity_gaps_json or "[]")[:8]],
            "",
            "Evidence limitations:",
            *[f"- {s}" for s in json.loads(report.limitations_json or "[]")[:8]],
            "",
            chart_summary,
        ]
        report.export_pdf_relpath = write_pdf_export(self.storage, assessment_id, version, pdf_lines)

        for action in assessment.improvement_actions:
            action.is_published = True
        self.lifecycle.transition(assessment, AssessmentStatus.PUBLISHED, actor_subject=published_by)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.published",
            message=f"Published report version {version}",
            actor_type="admin",
            actor_subject=published_by,
            details={"version": version, "export_json": report.export_json_relpath, "export_pdf": report.export_pdf_relpath},
        )
        self.db.flush()
        return report

    def get_published_results(self, assessment_id: str, version: int | None = None) -> PublishedResultsOut:
        report = self._get_report(assessment_id, version)
        assessment = self._require(assessment_id)
        scores = json.loads(report.scores_json)
        improvement = [
            ImprovementActionOut(
                id=item.get("id") or f"{report.id}-{idx}",
                title=item.get("title") or "",
                practice_key=item.get("practice_key"),
                domain_key=item.get("domain_key"),
                observation=item.get("observation") or "",
                supporting_evidence=item.get("supporting_evidence") or "",
                why_it_matters=item.get("why_it_matters") or "",
                recommended_action=item.get("recommended_action") or item.get("detail") or "",
                time_horizon=item.get("time_horizon") or "next_sprint",
                kpi=item.get("kpi") or "",
                priority=int(item.get("priority") or 3),
            )
            for idx, item in enumerate(json.loads(report.improvement_plan_json or "[]"))
        ]
        radar_raw = json.loads(report.radar_json or "[]")
        if radar_raw and isinstance(radar_raw, list) and "domain_key" in radar_raw[0]:
            radar = [DomainRadarPoint(**item) for item in radar_raw]
        else:
            radar = self.scoring.domain_rollups(assessment, use_final=True)
        heatmap_raw = json.loads(report.heatmap_json or "[]")
        if heatmap_raw and isinstance(heatmap_raw, list) and "practice_key" in heatmap_raw[0]:
            heatmap = [HeatmapCell(**item) for item in heatmap_raw]
        else:
            heatmap = self.scoring.heatmap(assessment, use_final=True)

        return PublishedResultsOut(
            assessment_id=assessment_id,
            version=report.version,
            title=report.title,
            team_name=assessment.team_name,
            product_service_name=assessment.product_service_name,
            published_at=report.published_at,
            lookback_days=report.lookback_days,
            evidence_influence_mode=report.evidence_influence_mode,
            overall_maturity=float(report.overall_maturity or 0),
            confidence_summary=report.confidence_summary or "Medium",
            evidence_quality=report.evidence_quality or "Adequate",
            practices_assessed=sum(1 for score in scores.values() if float(score) >= 1.5),
            strengths=json.loads(report.strengths_json or "[]"),
            maturity_gaps=json.loads(report.maturity_gaps_json or "[]"),
            evidence_limitations=json.loads(report.limitations_json or "[]"),
            radar=radar,
            heatmap=heatmap,
            improvement_actions=improvement,
            chart_summary=report.chart_summary,
            scores=scores,
        )

    def get_admin_comparison(self, assessment_id: str, version: int | None = None) -> AdminPublishedComparisonOut:
        report = self._get_report(assessment_id, version)
        comparison = json.loads(report.ai_vs_final_json or "{}")
        rows = [{"practice_key": key, **value} for key, value in comparison.items()]
        return AdminPublishedComparisonOut(
            assessment_id=assessment_id,
            version=report.version,
            ai_vs_final=rows,
            overall_maturity=report.overall_maturity,
        )

    def export_path(self, assessment_id: str, version: int, kind: str):
        report = self._get_report(assessment_id, version)
        rel = report.export_pdf_relpath if kind == "pdf" else report.export_json_relpath
        if not rel:
            raise AppError(code="export_missing", message="Export has not been generated", status_code=404)
        return resolve_export_path(self.storage, rel)

    def update_report(self, report_id: str, **_fields: object) -> PublishedReport:
        report = self.publications.get(report_id)
        if report is None:
            raise AppError(code="report_not_found", message="Published report not found", status_code=404)
        raise AppError(
            code="report_immutable",
            message="Published reports are immutable; publish a new version for corrections",
            status_code=409,
        )

    def _get_report(self, assessment_id: str, version: int | None) -> PublishedReport:
        if version is None:
            report = self.db.scalar(
                select(PublishedReport)
                .where(PublishedReport.assessment_id == assessment_id)
                .order_by(PublishedReport.version.desc())
            )
        else:
            report = self.db.scalar(
                select(PublishedReport).where(
                    PublishedReport.assessment_id == assessment_id,
                    PublishedReport.version == version,
                )
            )
        if report is None:
            raise AppError(code="report_not_found", message="Published report not found", status_code=404)
        return report

    def _require(self, assessment_id: str) -> Assessment:
        assessment = self.db.scalar(
            select(Assessment)
            .options(
                selectinload(Assessment.practice_coverages),
                selectinload(Assessment.improvement_actions),
            )
            .where(Assessment.id == assessment_id)
        )
        if assessment is None:
            raise AppError(code="assessment_not_found", message="Assessment not found", status_code=404)
        return assessment
