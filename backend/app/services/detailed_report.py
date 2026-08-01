from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Assessment, AssessmentReview
from app.models.evidence import EvidenceSnapshot
from app.schemas.detailed_report import (
    CrossCuttingTheme,
    DetailedAssessmentReport,
    DomainReview,
    EnterpriseStandardsReview,
    EvidenceLimitationsAppendix,
    ExecutiveNarrative,
    GenerationMetadata,
    LabeledClaim,
    MethodologySection,
    PracticeReview,
    RoadmapContextItem,
    SourceRef,
)
from app.services.audit import AuditService
from app.services.enterprise_standards import EnterpriseStandardsService


_SENSITIVE = re.compile(
    r"\b([A-Z]{2,10}-\d+)\b|\b[\w.+-]+@[\w.-]+\.\w+\b|pull request #\d+|PR #\d+",
    re.I,
)

DEFAULT_DOMAIN_ORDER = (
    ("continuous_exploration", "Continuous Exploration"),
    ("continuous_integration", "Continuous Integration"),
    ("continuous_deployment", "Continuous Deployment"),
    ("release_on_demand", "Release on Demand"),
)


def paraphrase(text: str, *, max_len: int = 500) -> str:
    cleaned = " ".join((text or "").split())
    cleaned = _SENSITIVE.sub("[redacted]", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def validate_detailed_report(
    report: DetailedAssessmentReport,
    *,
    practice_keys: set[str],
    standard_keys: set[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    seen_domains = {d.domain_key for d in report.domain_reviews}
    for key, _ in DEFAULT_DOMAIN_ORDER:
        if key not in seen_domains:
            warnings.append(f"missing_domain:{key}")
    report_keys = {p.practice_key for p in report.practice_reviews}
    for key in practice_keys:
        if key not in report_keys:
            warnings.append(f"missing_practice:{key}")
    for practice in report.practice_reviews:
        if practice.practice_key not in practice_keys:
            warnings.append(f"unknown_practice:{practice.practice_key}")
        for example in practice.practical_examples:
            if example.kind != "illustrative_example":
                warnings.append(f"unlabeled_example:{practice.practice_key}")
        if practice.final_score is not None and not (1.0 <= practice.final_score <= 5.0):
            warnings.append(f"score_out_of_range:{practice.practice_key}")
    if standard_keys:
        for key in report.enterprise_standards_review.aligned:
            if key not in standard_keys:
                warnings.append(f"unknown_standard:{key}")
    # Illustrative examples must never claim observed work without label.
    for domain in report.domain_reviews:
        for example in domain.illustrative_examples:
            if example.kind != "illustrative_example":
                warnings.append(f"domain_example_unlabeled:{domain.domain_key}")
    return warnings


class DetailedReportService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.model = get_assessment_model_config()
        self.enterprise = EnterpriseStandardsService(db)
        self.audit = AuditService(db)

    def _load_assessment(self, assessment_id: str) -> Assessment:
        assessment = self.db.scalar(
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.practice_coverages),
                selectinload(Assessment.improvement_actions),
                selectinload(Assessment.source_selection),
                selectinload(Assessment.evidence_snapshots)
                .selectinload(EvidenceSnapshot.metrics),
                selectinload(Assessment.evidence_snapshots)
                .selectinload(EvidenceSnapshot.limitations),
                selectinload(Assessment.interview_turns),
                selectinload(Assessment.reviews),
            )
        )
        if assessment is None:
            raise AppError(code="assessment_not_found", message="Assessment not found", status_code=404)
        return assessment

    def _dossier(self, assessment: Assessment) -> dict[str, Any]:
        selection = assessment.source_selection
        metrics: list[dict[str, Any]] = []
        limitations: list[str] = []
        if assessment.evidence_snapshots:
            snap = sorted(assessment.evidence_snapshots, key=lambda s: s.collected_at, reverse=True)[0]
            for metric in snap.metrics:
                metrics.append(
                    {
                        "key": metric.key,
                        "label": metric.label,
                        "value_text": metric.value_text,
                        "source_system": metric.source_system,
                        "ref": SourceRef(
                            ref_type="evidence_metric",
                            ref_key=metric.key,
                            label=metric.label,
                        ).model_dump(),
                    }
                )
            for lim in snap.limitations:
                limitations.append(lim.message)
        turns = []
        for turn in assessment.interview_turns or []:
            text = paraphrase(getattr(turn, "answer_text", None) or "")
            if not text:
                continue
            turns.append(
                {
                    "id": turn.id,
                    "text": text,
                    "ref": SourceRef(
                        ref_type="interview_turn", ref_key=str(turn.id), label="interview"
                    ).model_dump(),
                }
            )
        practices = []
        for coverage in assessment.practice_coverages:
            score = (
                coverage.admin_final_score
                if coverage.admin_final_score is not None
                else coverage.ai_candidate_score
            )
            practices.append(
                {
                    "practice_key": coverage.practice_key,
                    "domain_key": coverage.domain_key,
                    "score": score,
                    "maturity": coverage.named_maturity_level,
                    "ref": SourceRef(
                        ref_type="practice_coverage",
                        ref_key=coverage.practice_key,
                        label=coverage.practice_key,
                    ).model_dump(),
                }
            )
        enterprise = self.enterprise.published_section(assessment.id)
        return {
            "assessment": assessment,
            "selection": selection,
            "metrics": metrics,
            "limitations": limitations,
            "turns": turns,
            "practices": practices,
            "enterprise": enterprise,
            "actions": assessment.improvement_actions,
        }

    def generate(
        self,
        assessment_id: str,
        *,
        section: str | None = None,
        actor: str = "admin",
    ) -> DetailedAssessmentReport:
        assessment = self._load_assessment(assessment_id)
        dossier = self._dossier(assessment)
        existing = self.get_draft(assessment_id)
        report = existing or self._empty_report(dossier)
        statuses = dict(report.generation_metadata.section_statuses)

        stages = [
            "methodology",
            "domain_reviews",
            "practice_reviews",
            "cross_cutting_themes",
            "enterprise_standards_review",
            "roadmap_context",
            "evidence_limitations",
            "executive_narrative",
        ]
        targets = stages if not section else [section]
        for stage in targets:
            try:
                report = self._generate_stage(report, dossier, stage)
                statuses[stage] = "complete"
            except Exception as exc:  # noqa: BLE001
                statuses[stage] = "failed"
                report.generation_metadata.warnings.append(f"{stage}:{exc}")
                report.generation_metadata.incomplete = True

        practice_keys = {p["practice_key"] for p in dossier["practices"]} or self.model.practice_keys()
        standard_keys = {
            str(c.get("stable_key"))
            for c in (dossier["enterprise"].get("recommendation_cards") or [])
            if c.get("stable_key")
        }
        warnings = validate_detailed_report(
            report, practice_keys=practice_keys, standard_keys=standard_keys or None
        )
        report.generation_metadata.section_statuses = statuses
        report.generation_metadata.warnings = list(
            dict.fromkeys(report.generation_metadata.warnings + warnings)
        )
        report.generation_metadata.incomplete = report.generation_metadata.incomplete or bool(
            any(v == "failed" for v in statuses.values())
        )
        report.generation_metadata.generated_at = datetime.now(UTC).isoformat()
        report.generation_metadata.model_name = (
            self.settings.openai_assessment_model
            if self.settings.interview_provider == "live"
            else "mock"
        )
        self._save_draft(assessment_id, report, actor=actor)
        return report

    def get_draft(self, assessment_id: str) -> DetailedAssessmentReport | None:
        review = self._latest_review(assessment_id)
        if not review or not review.detailed_report_json:
            return None
        raw = json.loads(review.detailed_report_json)
        if review.detailed_report_edits_json:
            edits = json.loads(review.detailed_report_edits_json)
            raw = self._apply_edits(raw, edits)
        return DetailedAssessmentReport.model_validate(raw)

    def edit_section(
        self, assessment_id: str, *, section: str, content: dict[str, Any], actor: str
    ) -> DetailedAssessmentReport:
        review = self._latest_review(assessment_id)
        if review is None:
            raise AppError(code="review_missing", message="Review package not found", status_code=404)
        edits = json.loads(review.detailed_report_edits_json or "{}")
        edits[section] = {"content": content, "edited_by": actor, "edited_at": datetime.now(UTC).isoformat()}
        review.detailed_report_edits_json = json.dumps(edits)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="detailed_report.section_edited",
            message=f"Edited detailed report section {section}",
            actor_type="admin",
            actor_subject=actor,
            details={"section": section},
        )
        self.db.flush()
        draft = self.get_draft(assessment_id)
        if draft is None:
            raise AppError(code="detailed_report_missing", message="No detailed report draft", status_code=404)
        return draft

    def mark_example_unsuitable(
        self, assessment_id: str, *, section: str, example_index: int, actor: str
    ) -> DetailedAssessmentReport:
        draft = self.get_draft(assessment_id)
        if draft is None:
            raise AppError(code="detailed_report_missing", message="No detailed report draft", status_code=404)
        data = draft.model_dump()
        if section.startswith("domain:"):
            key = section.split(":", 1)[1]
            for domain in data["domain_reviews"]:
                if domain["domain_key"] == key and 0 <= example_index < len(domain["illustrative_examples"]):
                    domain["illustrative_examples"][example_index]["text"] = (
                        "[Example marked unsuitable by admin and removed from publication.]"
                    )
        self.edit_section(assessment_id, section=section, content=data, actor=actor)
        return self.get_draft(assessment_id)  # type: ignore[return-value]

    def _latest_review(self, assessment_id: str) -> AssessmentReview | None:
        assessment = self._load_assessment(assessment_id)
        if not assessment.reviews:
            return None
        return sorted(assessment.reviews, key=lambda r: r.created_at, reverse=True)[0]

    def _save_draft(
        self, assessment_id: str, report: DetailedAssessmentReport, *, actor: str
    ) -> None:
        review = self._latest_review(assessment_id)
        if review is None:
            review = AssessmentReview(assessment_id=assessment_id, reviewer_subject=actor)
            self.db.add(review)
            self.db.flush()
        review.detailed_report_json = report.model_dump_json()
        self.audit.record(
            assessment_id=assessment_id,
            event_type="detailed_report.generated",
            message="Detailed assessment report draft saved",
            actor_type="admin",
            actor_subject=actor,
            details={"incomplete": report.generation_metadata.incomplete},
        )
        self.db.flush()

    def _apply_edits(self, raw: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
        for section, payload in edits.items():
            content = payload.get("content")
            if not isinstance(content, dict):
                continue
            if section in raw and isinstance(content, dict) and section != "full":
                if section in {
                    "methodology",
                    "executive_narrative",
                    "enterprise_standards_review",
                    "evidence_limitations",
                    "generation_metadata",
                }:
                    raw[section] = content
                elif section == "domain_reviews" and isinstance(content.get("domain_reviews"), list):
                    raw["domain_reviews"] = content["domain_reviews"]
                elif section.startswith("domain:"):
                    key = section.split(":", 1)[1]
                    for idx, domain in enumerate(raw.get("domain_reviews") or []):
                        if domain.get("domain_key") == key:
                            raw["domain_reviews"][idx] = content
                else:
                    raw[section] = content.get(section, content)
            elif section == "full":
                raw = content
        return raw

    def _empty_report(self, dossier: dict[str, Any]) -> DetailedAssessmentReport:
        assessment: Assessment = dossier["assessment"]
        selection = dossier["selection"]
        return DetailedAssessmentReport(
            methodology=MethodologySection(
                team_product=f"{assessment.team_name} / {assessment.product_service_name}",
                evidence_period_days=assessment.lookback_days,
                jira_project=getattr(selection, "jira_project_key", None) if selection else None,
                ado_repository=getattr(selection, "ado_repository_name", None) if selection else None,
                ado_pipelines=[
                    p.get("name")
                    for p in json.loads(getattr(selection, "selected_pipelines_json", None) or "[]")
                    if p.get("name")
                ]
                if selection
                else [],
                participation_approach=assessment.participation_mode,
                evidence_influence_mode=assessment.evidence_influence_mode,
                framework_version=self.model.version,
                enterprise_standard_version=str(
                    dossier["enterprise"].get("catalog_version") or ""
                )
                or None,
                limitations=list(dossier["limitations"]),
            ),
            executive_narrative=ExecutiveNarrative(
                delivery_model="",
                next_maturity_transition="",
                confidence="Medium",
                narrative="Pending generation",
            ),
            enterprise_standards_review=EnterpriseStandardsReview(
                relationship_to_safe=(
                    "Enterprise findings are reported separately and do not alter SAFe maturity scores."
                )
            ),
            evidence_limitations=EvidenceLimitationsAppendix(confidence_explanation=""),
            generation_metadata=GenerationMetadata(
                model_name="mock",
                generated_at=datetime.now(UTC).isoformat(),
                section_statuses={},
            ),
        )

    def _generate_stage(
        self, report: DetailedAssessmentReport, dossier: dict[str, Any], stage: str
    ) -> DetailedAssessmentReport:
        assessment: Assessment = dossier["assessment"]
        data = report.model_dump()
        if stage == "methodology":
            return report  # already populated
        if stage == "domain_reviews":
            domain_reviews = []
            domain_order = [
                (d.key, d.name) for d in self.model.ordered_domains()
            ] or list(DEFAULT_DOMAIN_ORDER)
            for domain_key, domain_name in domain_order:
                practices = [p for p in dossier["practices"] if p.get("domain_key") == domain_key]
                scores = [p["score"] for p in practices if p.get("score") is not None]
                avg = sum(scores) / len(scores) if scores else None
                metric_claims = [
                    LabeledClaim(
                        kind="observed_evidence",
                        text=f"{m['label']}: {m['value_text']}",
                        source_refs=[SourceRef(**m["ref"])],
                    )
                    for m in dossier["metrics"][:4]
                ]
                human_claims = [
                    LabeledClaim(
                        kind="observed_evidence",
                        text=t["text"],
                        source_refs=[SourceRef(**t["ref"])],
                    )
                    for t in dossier["turns"][:3]
                ]
                domain_reviews.append(
                    DomainReview(
                        domain_key=domain_key,
                        domain_name=domain_name,
                        current_state_narrative=(
                            f"For {domain_name}, the assessment indicates "
                            f"{'an average maturity near ' + f'{avg:.1f}/5' if avg is not None else 'limited scored evidence'} "
                            f"based on interview responses and tool metrics from the selected lookback period."
                        ),
                        human_evidence=human_claims,
                        tool_evidence=metric_claims,
                        strengths=[
                            LabeledClaim(
                                kind="assessment_interpretation",
                                text=f"Relative strengths appear where practices in {domain_name} have higher reviewed scores.",
                                source_refs=[
                                    SourceRef(**p["ref"]) for p in practices if (p.get("score") or 0) >= 3
                                ][:3],
                            )
                        ],
                        gaps=[
                            LabeledClaim(
                                kind="assessment_interpretation",
                                text=f"Gaps remain where {domain_name} practices score below a consistent operating level.",
                                source_refs=[
                                    SourceRef(**p["ref"]) for p in practices if (p.get("score") or 5) < 3
                                ][:3],
                            )
                        ],
                        why_gaps_matter=[
                            LabeledClaim(
                                kind="assessment_interpretation",
                                text="Unresolved gaps in this domain slow feedback and increase delivery risk.",
                            )
                        ],
                        illustrative_examples=[
                            LabeledClaim(
                                kind="illustrative_example",
                                text=(
                                    f"Illustrative example: a team improving {domain_name} might introduce a single "
                                    "shared definition of done and measure cycle time weekly — this is an example, "
                                    "not something observed for this team."
                                ),
                            )
                        ],
                        progression_path=[
                            LabeledClaim(
                                kind="recommendation",
                                text=f"Progress {domain_name} by stabilizing one weak practice before expanding automation.",
                            )
                        ],
                        related_enterprise_standards=[
                            str(c.get("stable_key"))
                            for c in (dossier["enterprise"].get("recommendation_cards") or [])[:3]
                            if c.get("stable_key")
                        ],
                        confidence="Medium",
                        limitations=list(dossier["limitations"][:3]),
                    )
                )
            data["domain_reviews"] = [d.model_dump() for d in domain_reviews]
        elif stage == "practice_reviews":
            practice_meta = {p.key: p for _, p in self.model.ordered_practices()}
            reviews = []
            items = dossier["practices"] or [
                {
                    "practice_key": practice.key,
                    "domain_key": domain.key,
                    "score": None,
                    "maturity": None,
                    "ref": SourceRef(
                        ref_type="practice_coverage",
                        ref_key=practice.key,
                        label=practice.key,
                    ).model_dump(),
                }
                for domain, practice in self.model.ordered_practices()
            ]
            for item in items:
                meta = practice_meta.get(item["practice_key"])
                name = getattr(meta, "name", None) or item["practice_key"]
                related_actions = [
                    a.title
                    for a in dossier["actions"]
                    if a.practice_key == item["practice_key"]
                ]
                reviews.append(
                    PracticeReview(
                        practice_key=item["practice_key"],
                        practice_name=name,
                        domain_key=item.get("domain_key") or "",
                        maturity_level=item.get("maturity"),
                        final_score=float(item["score"]) if item.get("score") is not None else None,
                        interpretation=(
                            f"{name} is interpreted at "
                            f"{item.get('maturity') or 'an undetermined level'} "
                            f"from reviewed evidence for {assessment.team_name}."
                        ),
                        evidence_observed=[
                            LabeledClaim(
                                kind="observed_evidence",
                                text=f"{m['label']}: {m['value_text']}",
                                source_refs=[SourceRef(**m["ref"])],
                            )
                            for m in dossier["metrics"][:2]
                        ],
                        strengths=[
                            LabeledClaim(
                                kind="assessment_interpretation",
                                text="Strength signals come from higher reviewed scores and corroborating metrics where present.",
                                source_refs=[SourceRef(**item["ref"])],
                            )
                        ],
                        gaps=[
                            LabeledClaim(
                                kind="assessment_interpretation",
                                text="Gaps reflect inconsistent or manual steps described in the interview or missing tool evidence.",
                                source_refs=[SourceRef(**item["ref"])],
                            )
                        ],
                        better_could_look_like=[
                            LabeledClaim(
                                kind="assessment_interpretation",
                                text=f"A stronger version of {name} would show repeatable ownership, measurable outcomes, and fewer manual handoffs.",
                            )
                        ],
                        practical_examples=[
                            LabeledClaim(
                                kind="illustrative_example",
                                text=(
                                    f"Illustrative example only: for {name}, a team might publish a lightweight checklist "
                                    "and track one KPI for two sprints. This is not claimed as current team behavior."
                                ),
                            )
                        ],
                        recommendation=LabeledClaim(
                            kind="recommendation",
                            text=related_actions[0]
                            if related_actions
                            else f"Strengthen {name} with one measurable improvement in the next planning cycle.",
                        ),
                        related_action_titles=related_actions,
                        confidence="Medium",
                        source_refs=[SourceRef(**item["ref"])],
                    )
                )
            data["practice_reviews"] = [p.model_dump() for p in reviews]
        elif stage == "cross_cutting_themes":
            themes = [
                CrossCuttingTheme(
                    theme_key="flow_and_visibility",
                    title="Flow and work visibility",
                    narrative="Cross-domain evidence suggests visibility and flow constraints affect multiple practices.",
                    claims=[
                        LabeledClaim(
                            kind="assessment_interpretation",
                            text="Interview paraphrases and tool metrics indicate uneven flow signals across domains.",
                            source_refs=[
                                SourceRef(**m["ref"]) for m in dossier["metrics"][:2]
                            ],
                        )
                    ],
                ),
                CrossCuttingTheme(
                    theme_key="automation_and_quality",
                    title="Automation and quality",
                    narrative="Automation maturity appears uneven relative to quality feedback loops.",
                    claims=[
                        LabeledClaim(
                            kind="assessment_interpretation",
                            text="Where pipelines or issue completion metrics exist, they inform but do not alone prove quality practice maturity.",
                        )
                    ],
                ),
            ]
            data["cross_cutting_themes"] = [t.model_dump() for t in themes]
        elif stage == "enterprise_standards_review":
            enterprise = dossier["enterprise"]
            cards = enterprise.get("recommendation_cards") or []
            aligned = [c.get("stable_key") for c in cards if c.get("status") == "aligned" and c.get("stable_key")]
            partial = [
                c.get("stable_key")
                for c in cards
                if c.get("status") == "partially_aligned" and c.get("stable_key")
            ]
            findings = [c.get("stable_key") for c in cards if c.get("status") == "finding" and c.get("stable_key")]
            insufficient = [
                c.get("stable_key")
                for c in cards
                if c.get("status") == "insufficient_evidence" and c.get("stable_key")
            ]
            data["enterprise_standards_review"] = EnterpriseStandardsReview(
                aligned=[str(x) for x in aligned],
                partial=[str(x) for x in partial],
                findings=[str(x) for x in findings],
                insufficient_evidence=[str(x) for x in insufficient],
                relationship_to_safe=(
                    "Enterprise findings remain separate from SAFe practice scores and never alter the maturity radar."
                ),
                recommendations=[
                    LabeledClaim(
                        kind="recommendation",
                        text=paraphrase(c.get("recommendation") or c.get("observation") or ""),
                        source_refs=[
                            SourceRef(
                                ref_type="enterprise_finding",
                                ref_key=str(c.get("stable_key") or "enterprise"),
                                label=str(c.get("standard") or c.get("stable_key") or "standard"),
                            )
                        ],
                    )
                    for c in cards[:8]
                    if c.get("recommendation") or c.get("observation")
                ],
            ).model_dump()
        elif stage == "roadmap_context":
            items = []
            for action in dossier["actions"][:12]:
                items.append(
                    RoadmapContextItem(
                        action_title=action.title,
                        observed_problem=paraphrase(action.observation or action.detail or action.title),
                        why_selected="Selected from reviewed SAFe/enterprise improvement actions with highest priority.",
                        expected_benefit=paraphrase(action.why_it_matters or "Improves delivery predictability."),
                        implementation_example=LabeledClaim(
                            kind="illustrative_example",
                            text=(
                                "Illustrative implementation example: start with a two-week pilot, define a success metric, "
                                "and review outcomes in the next planning event. Not observed as completed work."
                            ),
                        ),
                        owner_type=action.owner_hint or "practice owner / platform engineer",
                        dependencies=[],
                        kpi_signal=action.kpi or "Define a measurable validation signal before starting.",
                        related_practice_keys=[action.practice_key] if action.practice_key else [],
                        related_standard_keys=[],
                        time_horizon=action.time_horizon,
                    )
                )
            data["roadmap_context"] = [i.model_dump() for i in items]
        elif stage == "evidence_limitations":
            data["evidence_limitations"] = EvidenceLimitationsAppendix(
                evidence_sources=["interview", "jira", "azure_devops", "enterprise_standards"],
                metrics_used=[m["key"] for m in dossier["metrics"]],
                missing_or_unreliable=list(dossier["limitations"]),
                contradictions=[],
                interview_primary_areas=["culture", "collaboration", "decision making"],
                tool_primary_areas=["flow metrics", "pipeline outcomes", "change linkage"],
                excluded_data=["issue titles", "commit messages", "PR names", "usernames", "emails"],
                confidence_explanation=(
                    "Confidence reflects corroboration between paraphrased interview answers and aggregated tool metrics; "
                    "areas with missing catalogs or skipped sources are marked as limitations."
                ),
            ).model_dump()
        elif stage == "executive_narrative":
            strengths = [
                p["practice_key"]
                for p in dossier["practices"]
                if (p.get("score") or 0) >= 3.5
            ][:5]
            constraints = [
                p["practice_key"]
                for p in dossier["practices"]
                if (p.get("score") or 5) < 2.5
            ][:5]
            data["executive_narrative"] = ExecutiveNarrative(
                delivery_model=(
                    f"{assessment.team_name} delivers {assessment.product_service_name} using a mixed "
                    f"interview-and-tool evidence model over {assessment.lookback_days} days."
                ),
                strongest_capabilities=strengths,
                recurring_constraints=constraints,
                cross_domain_themes=["flow_and_visibility", "automation_and_quality"],
                next_maturity_transition=(
                    "Stabilize the weakest cross-cutting constraint, then raise adjacent practices one level."
                ),
                confidence="Medium",
                narrative=(
                    f"Overall, {assessment.team_name} shows a delivery system with identifiable strengths and "
                    f"recurring constraints. Stronger practices cluster around {', '.join(strengths) or 'a limited set'}, "
                    f"while {', '.join(constraints) or 'several practices'} remain inconsistent or under-evidenced. "
                    "The likely next maturity transition is to make one cross-cutting improvement measurable before "
                    "broadening automation. This narrative synthesizes reviewed scores, paraphrased interview answers, "
                    "and aggregated tool metrics without inventing unobserved incidents or tools."
                ),
            ).model_dump()
        return DetailedAssessmentReport.model_validate(data)
