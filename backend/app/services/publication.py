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
from app.services.detailed_report import DetailedReportService
from app.services.enterprise_standards import EnterpriseStandardsService
from app.services.exports import resolve_export_path, write_json_export, write_pdf_export
from app.services.lifecycle import LifecycleService
from app.services.scoring import ScoringService
from app.services.storage import StorageService


def _norm_rec(text: str) -> str:
    cleaned = " ".join((text or "").lower().split())
    for token in (
        "the team should ",
        "the team must ",
        "please ",
        "should ",
        "must ",
        "recommend ",
        "ensure ",
        "the team ",
    ):
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()


def _token_set(text: str) -> set[str]:
    return {tok for tok in _norm_rec(text).split() if len(tok) > 2}


def _recs_overlap(a: str, b: str) -> bool:
    """True when recommendations describe the same underlying action."""
    na, nb = _norm_rec(a), _norm_rec(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    union = len(ta | tb)
    return overlap >= 3 and (overlap / union) >= 0.45


def build_consolidated_improvement_plan(
    safe_actions: list[dict],
    enterprise_cards: list[dict],
) -> list[dict]:
    """Merge overlapping SAFe and enterprise recommendations into single actions.

    Preserves related practice and standard references. Enterprise findings never
    change SAFe maturity scores; this only consolidates recommended actions.
    """
    plan: list[dict] = []
    for action in safe_actions:
        practice_keys = []
        if action.get("practice_key"):
            practice_keys.append(str(action["practice_key"]))
        plan.append(
            {
                **action,
                "related_practice_keys": practice_keys,
                "related_standard_keys": [],
                "related_standard_titles": [],
                "sources": ["safe"],
            }
        )

    for card in enterprise_cards:
        rec = (card.get("recommendation") or "").strip()
        if not rec:
            continue
        standard_key = str(card.get("stable_key") or "")
        standard_title = str(card.get("standard") or standard_key or "Enterprise standard")
        practice_keys = [str(p) for p in (card.get("related_safe_practices") or []) if p]
        merged = False
        for item in plan:
            existing_rec = item.get("recommended_action") or item.get("title") or ""
            shared_practice = bool(
                set(item.get("related_practice_keys") or []) & set(practice_keys)
            )
            soft_overlap = (
                shared_practice
                and len(_token_set(existing_rec) & _token_set(rec)) >= 2
            )
            if _recs_overlap(existing_rec, rec) or soft_overlap:
                # Merge into existing action; keep the richer recommendation text.
                if len(rec) > len(existing_rec):
                    item["recommended_action"] = rec
                if card.get("observation") and card.get("observation") not in (
                    item.get("observation") or ""
                ):
                    base = (item.get("observation") or "").strip()
                    item["observation"] = (
                        f"{base} {card['observation']}".strip() if base else card["observation"]
                    )
                if card.get("supporting_evidence"):
                    evidence = item.get("supporting_evidence") or ""
                    extra = card["supporting_evidence"]
                    if extra and extra not in evidence:
                        item["supporting_evidence"] = (
                            f"{evidence}; {extra}".strip("; ") if evidence else extra
                        )
                for pk in practice_keys:
                    if pk not in item["related_practice_keys"]:
                        item["related_practice_keys"].append(pk)
                if standard_key and standard_key not in item["related_standard_keys"]:
                    item["related_standard_keys"].append(standard_key)
                if standard_title and standard_title not in item["related_standard_titles"]:
                    item["related_standard_titles"].append(standard_title)
                if "enterprise" not in item["sources"]:
                    item["sources"].append("enterprise")
                if not item.get("practice_key") and practice_keys:
                    item["practice_key"] = practice_keys[0]
                # Prefer earlier/urgent horizon when merging.
                card_horizon = card.get("suggested_time_horizon") or "next_sprint"
                horizon_rank = {"next_sprint": 0, "ninety_days": 1, "longer_term": 2, "this_pi": 1}
                if horizon_rank.get(card_horizon, 9) < horizon_rank.get(
                    item.get("time_horizon") or "next_sprint", 9
                ):
                    item["time_horizon"] = card_horizon
                if card.get("requirement_level") == "required":
                    item["priority"] = min(int(item.get("priority") or 3), 2)
                merged = True
                break
        if merged:
            continue
        plan.append(
            {
                "id": f"enterprise-{standard_key or len(plan)}",
                "title": standard_title,
                "practice_key": practice_keys[0] if practice_keys else None,
                "domain_key": None,
                "observation": card.get("observation") or "",
                "supporting_evidence": card.get("supporting_evidence") or "",
                "why_it_matters": f"Enterprise standard ({card.get('requirement_level') or 'preferred'})",
                "recommended_action": rec,
                "time_horizon": card.get("suggested_time_horizon") or "next_sprint",
                "kpi": "",
                "priority": 2 if card.get("requirement_level") == "required" else 3,
                "related_practice_keys": practice_keys,
                "related_standard_keys": [standard_key] if standard_key else [],
                "related_standard_titles": [standard_title],
                "sources": ["enterprise"],
            }
        )
    return plan


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
        self.enterprise = EnterpriseStandardsService(db)

    def publish(self, assessment_id: str, *, published_by: str = "admin") -> PublishedReport:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.ADMIN_REVIEW:
            raise AppError(
                code="invalid_state",
                message="Assessment must be in admin_review to publish",
                status_code=409,
            )

        review = self.db.scalar(
            select(AssessmentReview)
            .where(AssessmentReview.assessment_id == assessment_id)
            .order_by(AssessmentReview.created_at.desc())
        )
        if review is None or not review.ready_to_publish:
            raise AppError(
                code="review_not_approved",
                message="Approve the review package before publishing",
                status_code=409,
            )

        scores: dict[str, float] = {}
        ai_vs_final: dict[str, dict] = {}
        for coverage in assessment.practice_coverages:
            final = (
                coverage.admin_final_score
                if coverage.admin_final_score is not None
                else coverage.ai_candidate_score
            )
            if final is None:
                raise AppError(
                    code="scores_incomplete",
                    message="All practices need a final or candidate score before publication",
                    status_code=400,
                )
            scores[coverage.practice_key] = float(final)
            ai_vs_final[coverage.practice_key] = {
                "ai_candidate_score": coverage.ai_candidate_score,
                "admin_final_score": coverage.admin_final_score
                if coverage.admin_final_score is not None
                else float(final),
                "admin_rationale": coverage.admin_rationale,
                "named_maturity_level": coverage.named_maturity_level,
            }

        radar = self.scoring.domain_rollups(assessment, use_final=True)
        heatmap = self.scoring.heatmap(assessment, use_final=True)
        overall = (
            review.overall_maturity
            if review.overall_maturity is not None
            else self.scoring.weighted_overall(radar)
        )
        chart_summary = review.notes or (
            f"Overall maturity {overall}/5.0 across four SAFe DevOps domains with "
            f"{sum(1 for s in scores.values() if s >= 2.0)} practices assessed."
        )

        # Enterprise findings are published separately and never alter SAFe scores.
        enterprise = self.enterprise.published_section(assessment_id)
        safe_actions = [
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
        improvement_plan = build_consolidated_improvement_plan(
            safe_actions,
            list(enterprise.get("recommendation_cards") or []),
        )

        detailed_service = DetailedReportService(self.db)
        detailed = detailed_service.get_draft(assessment_id)
        if detailed is None:
            detailed = detailed_service.generate(assessment_id, actor=published_by)
        detailed_payload = detailed.model_dump()
        detailed_incomplete = bool(detailed.generation_metadata.incomplete)

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
            model_name=next(
                (
                    c.scoring_model_version
                    for c in assessment.practice_coverages
                    if c.scoring_model_version
                ),
                "mock",
            ),
            ai_vs_final_json=json.dumps(ai_vs_final),
            chart_summary=chart_summary,
            enterprise_standards_json=json.dumps(enterprise),
            detailed_report_json=json.dumps(detailed_payload),
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
            "enterprise_standards": enterprise,
            "detailed_review": detailed_payload,
            "detailed_review_incomplete": detailed_incomplete,
        }
        # Public export must never include AI candidate comparison or numeric enterprise scores.
        dumped = json.dumps(public_payload)
        assert "ai_candidate_score" not in dumped
        assert "enterprise_alignment_score" not in dumped
        assert "numeric_enterprise" not in dumped

        report.export_json_relpath = write_json_export(
            self.storage, assessment_id, version, public_payload
        )
        pdf_lines = [
            report.title,
            f"Version {version} · Published {report.published_at.date().isoformat()}",
            "",
            "1. Cover and assessment scope",
            f"Team/product: {assessment.team_name} / {assessment.product_service_name}",
            f"Evidence period: {assessment.lookback_days} days",
            f"Evidence influence mode: {assessment.evidence_influence_mode}",
            "",
            "2. Executive summary",
            detailed.executive_narrative.narrative[:2000],
            "",
            "3. SAFe DevOps Maturity (radar/heatmap summarized)",
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
            "",
            "2. Enterprise Standards Findings",
            (
                f"- Applicable {enterprise.get('applicable_count', 0)}; "
                f"aligned {enterprise.get('aligned_count', 0)}; "
                f"partial {enterprise.get('partially_aligned_count', 0)}; "
                f"findings {enterprise.get('finding_count', 0)}; "
                f"insufficient evidence {enterprise.get('insufficient_evidence_count', 0)}"
            ),
            "Enterprise findings do not alter the SAFe maturity score.",
        ]
        for card in (enterprise.get("recommendation_cards") or [])[:8]:
            pdf_lines.append(
                f"- {card.get('standard')} ({card.get('requirement_level')}, {card.get('status')}): "
                f"{card.get('observation') or card.get('recommendation')}"
            )
        pdf_lines.extend(["", "4. Key actions / Consolidated Improvement Plan"])
        for item in improvement_plan[:12]:
            practices = ", ".join(item.get("related_practice_keys") or []) or "-"
            standards = (
                ", ".join(
                    item.get("related_standard_titles")
                    or item.get("related_standard_keys")
                    or []
                )
                or "-"
            )
            pdf_lines.append(
                f"- {item.get('title')}: {item.get('recommended_action')} "
                f"[practices: {practices}; standards: {standards}]"
            )
        if detailed_incomplete:
            pdf_lines.extend(
                [
                    "",
                    "WARNING: Detailed Assessment Review is incomplete. "
                    "Some sections failed generation and should be regenerated before relying on depth.",
                ]
            )
        pdf_lines.extend(["", "5. Detailed domain reviews"])
        for domain in detailed.domain_reviews:
            pdf_lines.append(f"- {domain.domain_name}: {domain.current_state_narrative[:500]}")
            for example in domain.illustrative_examples[:1]:
                pdf_lines.append(f"  Illustrative example: {example.text[:400]}")
        pdf_lines.extend(["", "6. Practice drill-downs"])
        for practice in detailed.practice_reviews[:16]:
            pdf_lines.append(
                f"- {practice.practice_name} ({practice.final_score}): {practice.interpretation[:300]}"
            )
        pdf_lines.extend(["", "7. Enterprise standards"])
        pdf_lines.append(detailed.enterprise_standards_review.relationship_to_safe)
        pdf_lines.extend(["", "8. Roadmap and KPIs"])
        for item in detailed.roadmap_context[:10]:
            pdf_lines.append(
                f"- {item.action_title} [{item.time_horizon}] KPI: {item.kpi_signal}"
            )
        pdf_lines.extend(["", "9. Evidence and limitations"])
        pdf_lines.append(detailed.evidence_limitations.confidence_explanation[:800])
        for lim in detailed.evidence_limitations.missing_or_unreliable[:8]:
            pdf_lines.append(f"- {lim}")
        report.export_pdf_relpath = write_pdf_export(
            self.storage, assessment_id, version, pdf_lines
        )

        for action in assessment.improvement_actions:
            action.is_published = True
        self.lifecycle.transition(
            assessment, AssessmentStatus.PUBLISHED, actor_subject=published_by
        )
        self.audit.record(
            assessment_id=assessment_id,
            event_type="assessment.published",
            message=f"Published report version {version}",
            actor_type="admin",
            actor_subject=published_by,
            details={
                "version": version,
                "export_json": report.export_json_relpath,
                "export_pdf": report.export_pdf_relpath,
            },
        )
        self.db.flush()
        return report

    def get_published_results(
        self, assessment_id: str, version: int | None = None
    ) -> PublishedResultsOut:
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
                related_practice_keys=list(item.get("related_practice_keys") or (
                    [item["practice_key"]] if item.get("practice_key") else []
                )),
                related_standard_keys=list(item.get("related_standard_keys") or []),
                related_standard_titles=list(item.get("related_standard_titles") or []),
                sources=list(item.get("sources") or ["safe"]),
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

        detailed_raw = None
        detailed_incomplete = False
        if report.detailed_report_json:
            try:
                detailed_raw = json.loads(report.detailed_report_json)
                detailed_incomplete = bool(
                    (detailed_raw.get("generation_metadata") or {}).get("incomplete")
                )
            except json.JSONDecodeError:
                detailed_raw = None
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
            enterprise_standards=json.loads(report.enterprise_standards_json or "{}")
            or self.enterprise.published_section(assessment_id),
            detailed_review=detailed_raw,
            detailed_review_incomplete=detailed_incomplete,
        )

    def get_admin_comparison(
        self, assessment_id: str, version: int | None = None
    ) -> AdminPublishedComparisonOut:
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
            raise AppError(
                code="export_missing", message="Export has not been generated", status_code=404
            )
        return resolve_export_path(self.storage, rel)

    def update_report(self, report_id: str, **_fields: object) -> PublishedReport:
        report = self.publications.get(report_id)
        if report is None:
            raise AppError(
                code="report_not_found", message="Published report not found", status_code=404
            )
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
            raise AppError(
                code="report_not_found", message="Published report not found", status_code=404
            )
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
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return assessment
