from __future__ import annotations

from typing import Any

from app.assessment_config import get_assessment_model_config
from app.schemas.scoring import CandidateScoringAI, ImprovementActionAI, PracticeScoreAI


class MockScoringProvider:
    name = "mock"

    def score_assessment(
        self, context: dict[str, Any]
    ) -> tuple[CandidateScoringAI, dict[str, Any]]:
        model = get_assessment_model_config()
        coverage_states: dict[str, str] = context.get("coverage_states") or {}
        turn_ids: dict[str, list[str]] = context.get("source_turn_ids") or {}
        influence = context.get("influence_mode") or "balanced"
        limitations = list(context.get("evidence_limitations") or [])
        if context.get("integration_failures"):
            # Integration failures are limitations, not low maturity.
            for item in context["integration_failures"]:
                limitations.append(f"Integration limitation (not a maturity signal): {item}")

        practice_scores: list[PracticeScoreAI] = []
        for domain, practice in model.ordered_practices():
            state = coverage_states.get(practice.key, "not_discussed")
            base = {
                "sufficient": 3.5,
                "partial": 2.5,
                "clarify": 2.0,
                "not_discussed": 1.5,
            }.get(state, 2.0)
            # Mild influence from evidence mode without treating missing tools as low maturity.
            if influence == "evidence_led" and state in {"sufficient", "partial"}:
                base = min(5.0, base + 0.2)
            if influence == "context_only":
                base = max(1.0, base - 0.1)
            score = round(min(5.0, max(1.0, base)), 1)
            level = next(
                (lvl.name for lvl in model.maturity_levels if abs(lvl.score - round(score)) < 0.51),
                "Managed",
            )
            practice_scores.append(
                PracticeScoreAI(
                    practice_key=practice.key,
                    coverage_state=state,  # type: ignore[arg-type]
                    ai_candidate_score=score,
                    named_maturity_level=level,
                    confidence=0.72 if state != "not_discussed" else 0.35,
                    human_evidence="Workshop discussion referenced this practice."
                    if state != "not_discussed"
                    else "",
                    jira_evidence="Jira signals available where collection succeeded."
                    if not context.get("jira_failed")
                    else "",
                    ado_evidence="Azure DevOps signals available where collection succeeded."
                    if not context.get("ado_failed")
                    else "",
                    source_turn_ids=turn_ids.get(practice.key, [])[:8],
                    contradictions=[],
                    limitations=[
                        lim
                        for lim in limitations
                        if practice.key in lim.lower() or "integration" in lim.lower()
                    ][:4],
                    rationale=f"Rubric-aligned draft score for {practice.name} under {influence} influence.",
                    missing_information=["More concrete examples needed"]
                    if state in {"partial", "clarify", "not_discussed"}
                    else [],
                    recommendation=practice.improvement_guidance[0]
                    if practice.improvement_guidance
                    else "",
                )
            )

        scored = [p for p in practice_scores if p.coverage_state != "not_discussed"]
        overall = (
            round(sum(p.ai_candidate_score for p in scored) / max(len(scored), 1), 1)
            if scored
            else 1.5
        )
        gaps = [p.practice_key for p in practice_scores if p.ai_candidate_score <= 2.5][:6]
        strengths = [p.practice_key for p in practice_scores if p.ai_candidate_score >= 3.5][:5]

        actions: list[ImprovementActionAI] = []
        for p in sorted(practice_scores, key=lambda x: x.ai_candidate_score)[:5]:
            if p.coverage_state == "not_discussed" and len(actions) >= 3:
                continue
            domain_key = next(
                d.key for d, pr in model.ordered_practices() if pr.key == p.practice_key
            )
            horizon = (
                "next_sprint"
                if p.ai_candidate_score <= 2.0
                else "ninety_days"
                if p.ai_candidate_score <= 3.0
                else "longer_term"
            )
            guidance = model.require_practice(p.practice_key).improvement_guidance[0]
            kpi = model.require_practice(p.practice_key).kpi_guidance[0]
            actions.append(
                ImprovementActionAI(
                    title=guidance[:240],
                    observation=p.human_evidence
                    or f"Coverage for {p.practice_key} is {p.coverage_state}.",
                    practice_key=p.practice_key,
                    domain_key=domain_key,
                    supporting_evidence=(p.jira_evidence or p.ado_evidence or "Workshop notes")[
                        :2000
                    ],
                    why_it_matters=f"Improving {p.practice_key} raises delivery reliability and reduces risk.",
                    recommended_action=guidance,
                    time_horizon=horizon,  # type: ignore[arg-type]
                    kpi=kpi[:240],
                    priority=1
                    if p.ai_candidate_score <= 2.0
                    else 2
                    if p.ai_candidate_score <= 3.0
                    else 3,
                )
            )

        result = CandidateScoringAI(
            practice_scores=practice_scores,
            overall_maturity=overall,
            confidence_summary="High"
            if len(scored) >= 10
            else "Medium"
            if len(scored) >= 6
            else "Low",
            evidence_quality="Limited" if limitations else "Adequate",
            strengths=[f"Strength in {k}" for k in strengths],
            maturity_gaps=[f"Gap in {k}" for k in gaps],
            evidence_limitations=limitations[:12] or ["No material evidence limitations recorded."],
            improvement_actions=actions,
            chart_summary=(
                f"Overall maturity {overall}/5.0 across four SAFe DevOps domains. "
                f"{len(scored)} practices have interview coverage; gaps concentrate in lower-scoring practices."
            ),
        )
        telemetry = {
            "provider": self.name,
            "model": "mock-scoring",
            "reasoning_effort": "n/a",
            "latency_ms": 5,
            "prompt_config_version": model.version,
        }
        return result, telemetry
