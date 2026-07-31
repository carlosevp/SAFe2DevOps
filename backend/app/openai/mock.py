from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from app.models.enums import CoverageState
from app.schemas.interview import InterviewAnalysisAI, OpeningQuestionAI, PracticeUpdateAI

PRACTICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hypothesize": ("hypothesis", "experiment", "bet", "assumption", "idea"),
    "collaborate_research": ("research", "customer", "stakeholder", "discovery", "interview"),
    "architect": ("architecture", "design", "nfr", "non-functional", "pattern"),
    "synthesize": ("roadmap", "priorit", "backlog grooming", "synthesize"),
    "develop": ("feature branch", "trunk", "pair", "tdd", "code review", "pull request", "pr "),
    "build": ("pipeline", "ci ", "build", "quality gate", "compile"),
    "test_end_to_end": ("end-to-end", "e2e", "integration test", "automated test", "test suite"),
    "stage": ("staging", "pre-prod", "preprod", "uat"),
    "deploy": ("deploy", "release train", "cd ", "promotion", "production deploy"),
    "verify": ("smoke", "verify", "health check", "post-deploy"),
    "monitor": ("monitor", "dashboard", "alert", "observability", "telemetry"),
    "respond": ("incident", "rollback", "hotfix", "on-call", "recover"),
    "release": ("feature flag", "feature toggle", "release", "dark launch"),
    "stabilize": ("stabilize", "canary", "gradual", "blast radius"),
    "measure": ("kpi", "metric", "outcome", "measure value", "okr"),
    "learn": ("retro", "learn", "feedback loop", "postmortem", "inspect and adapt"),
}

DOMAIN_FOR = {
    "hypothesize": "continuous_exploration",
    "collaborate_research": "continuous_exploration",
    "architect": "continuous_exploration",
    "synthesize": "continuous_exploration",
    "develop": "continuous_integration",
    "build": "continuous_integration",
    "test_end_to_end": "continuous_integration",
    "stage": "continuous_integration",
    "deploy": "continuous_deployment",
    "verify": "continuous_deployment",
    "monitor": "continuous_deployment",
    "respond": "continuous_deployment",
    "release": "release_on_demand",
    "stabilize": "release_on_demand",
    "measure": "release_on_demand",
    "learn": "release_on_demand",
}


class MockInterviewProvider:
    """Deterministic interview AI for development, tests, and demos."""

    name = "mock"

    def generate_opening_question(
        self, context: dict[str, Any]
    ) -> tuple[OpeningQuestionAI, dict[str, Any]]:
        started = time.perf_counter()
        team = context.get("team_name") or "the team"
        product = context.get("product_service_name") or "the product"
        jira = context.get("jira_project_key") or "the Jira project"
        repo = context.get("ado_repository_name") or "the repository"
        days = context.get("lookback_days") or 90
        evidence = context.get("evidence_summary") or "Recent delivery evidence is available."
        question = (
            f"Think of a recent, representative change {team} delivered for {product}. "
            f"Using work from {jira} and {repo} over the last {days} days as context, "
            "walk us through how it moved from the initial need or idea through development, "
            "testing, deployment, release, and learning afterward."
        )
        opening = OpeningQuestionAI(
            question_text=question,
            why_asking=(
                "A single end-to-end story reveals how discovery, integration, deployment, "
                "and learning actually work together—without walking through a fixed checklist."
            ),
            evidence_context=evidence[:800],
            topic_label="Delivery journey",
        )
        telemetry = {
            "provider": self.name,
            "model": "mock-interview",
            "reasoning_effort": "none",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "input_tokens": 0,
            "output_tokens": len(question.split()),
        }
        return opening, telemetry

    def analyze_answer(self, context: dict[str, Any]) -> tuple[InterviewAnalysisAI, dict[str, Any]]:
        started = time.perf_counter()
        answer = (context.get("answer_text") or "").strip()
        lower = answer.lower()
        known_keys: set[str] = set(context.get("known_practice_keys") or PRACTICE_KEYWORDS.keys())
        coverage_map: dict[str, str] = dict(context.get("coverage_states") or {})
        influence = context.get("influence_mode") or "balanced"
        is_clarification = bool(context.get("is_clarification"))
        pending = (context.get("pending_clarification") or "").lower()

        matched: list[str] = []
        for key, words in PRACTICE_KEYWORDS.items():
            if key not in known_keys:
                continue
            if any(w in lower for w in words):
                matched.append(key)

        # Opening-story answers often cover CI/CD path even with sparse keywords.
        if not matched and len(answer.split()) >= 40:
            matched = ["develop", "build", "deploy", "verify"]

        word_count = len(answer.split())
        needs_clarification = False
        clarification: str | None = None

        if word_count < 25 and not is_clarification:
            needs_clarification = True
            clarification = (
                "Can you walk through one concrete recent change—who started it, "
                "how it was built and tested, and how it reached users?"
            )
        elif ("pipeline" in lower or "pull request" in lower or "pr " in lower) and not any(
            token in lower for token in ("block", "gate", "fail", "required check", "cannot merge")
        ):
            if (
                not is_clarification
                or "quality gate" in pending
                or "blocked" in pending
                or "fail" in pending
            ):
                needs_clarification = True
                clarification = (
                    "Are pull requests blocked from merging when the build or a quality gate fails?"
                )

        if is_clarification and (
            "yes" in lower or "block" in lower or "fail" in lower or "required" in lower
        ):
            if "build" not in matched:
                matched.append("build")
            needs_clarification = False
            clarification = None

        updates: list[PracticeUpdateAI] = []
        contradictions: list[str] = []
        open_gaps: list[str] = []

        for key in matched:
            state = CoverageState.SUFFICIENT
            conf = 0.72 if word_count >= 40 else 0.5
            gaps: list[str] = []
            contras: list[str] = []
            if (
                key == "build"
                and needs_clarification
                and clarification
                and "quality gate" in clarification.lower()
            ):
                state = CoverageState.CLARIFY
                conf = 0.45
                gaps.append("Whether failed quality gates prevent merging")
            elif word_count < 40:
                state = CoverageState.PARTIAL
                conf = 0.48
                gaps.append(f"More detail on how {key.replace('_', ' ')} works day to day")
            if influence == "evidence_led" and context.get("tool_signals"):
                signals = context["tool_signals"]
                if key in {"build", "deploy"} and signals.get("pipeline_success_rate", 100) < 80:
                    contras.append(
                        "Tool evidence shows unstable pipelines while the team described smooth delivery"
                    )
                    contradictions.append(contras[-1])
                    if state == CoverageState.SUFFICIENT:
                        state = CoverageState.CLARIFY
                        needs_clarification = True
                        clarification = clarification or (
                            "Your tools show frequent pipeline failures—how does that square with the delivery flow you described?"
                        )
            if influence == "context_only":
                # Evidence shapes confidence only; do not escalate contradictions from tools.
                contras = []
            score = (
                3.0
                if state == CoverageState.SUFFICIENT
                else 2.0
                if state == CoverageState.PARTIAL
                else None
            )
            updates.append(
                PracticeUpdateAI(
                    practice_key=key,
                    coverage_state=state,
                    evidence_summary=f"Team described aspects of {key.replace('_', ' ')}.",
                    confidence=conf,
                    open_gaps=gaps,
                    contradictions=contras,
                    candidate_score=score,
                )
            )
            open_gaps.extend(gaps)
            coverage_map[key] = state.value

        if not updates and not needs_clarification:
            needs_clarification = True
            clarification = "What happens after code is merged—how do you test, deploy, and learn whether the change helped?"

        next_q, reason = self._next_question(coverage_map, known_keys, matched)
        sufficient = sum(1 for v in coverage_map.values() if v == CoverageState.SUFFICIENT.value)
        recommendation: str = "continue"
        if sufficient >= 12:
            recommendation = "complete"
        elif sufficient >= 8:
            recommendation = "checkpoint"

        covered_names = [
            k.replace("_", " ")
            for k, u in ((u.practice_key, u) for u in updates)
            if u.coverage_state == CoverageState.SUFFICIENT
        ]
        partial_names = [
            k.replace("_", " ")
            for k, u in ((u.practice_key, u) for u in updates)
            if u.coverage_state == CoverageState.PARTIAL
        ]
        summary_bits = []
        if covered_names:
            summary_bits.append(f"This covered {', '.join(covered_names[:3])}")
        if partial_names:
            summary_bits.append(f"partially covered {', '.join(partial_names[:2])}")
        coverage_summary = (
            ". ".join(summary_bits) + "." if summary_bits else "Limited coverage from this answer."
        )

        analysis = InterviewAnalysisAI(
            response_summary=self._summary(answer),
            claims=self._claims(answer),
            source_attribution=["room_typed"],
            practice_updates=updates,
            evidence_summary=str(context.get("evidence_summary") or "")[:1000],
            confidence=0.7 if updates else 0.4,
            open_gaps=open_gaps,
            contradictions=contradictions,
            needs_immediate_clarification=needs_clarification,
            clarification_question=clarification if needs_clarification else None,
            next_best_question=next_q,
            reason_for_next_question=reason,
            completion_recommendation=recommendation,  # type: ignore[arg-type]
            overall_coverage_summary=coverage_summary,
        )
        telemetry = {
            "provider": self.name,
            "model": "mock-interview",
            "reasoning_effort": "none",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "input_tokens": len(answer.split()),
            "output_tokens": len(analysis.response_summary.split()),
            "fingerprint": hashlib.sha256(answer.encode()).hexdigest()[:12],
        }
        return analysis, telemetry

    def _next_question(
        self, coverage_map: dict[str, str], known: set[str], matched: list[str]
    ) -> tuple[str, str]:
        priority = [
            "hypothesize",
            "collaborate_research",
            "develop",
            "build",
            "test_end_to_end",
            "deploy",
            "verify",
            "monitor",
            "respond",
            "release",
            "measure",
            "learn",
            "architect",
            "synthesize",
            "stage",
            "stabilize",
        ]
        for key in priority:
            if key not in known:
                continue
            state = coverage_map.get(key, CoverageState.NOT_DISCUSSED.value)
            if state in {
                CoverageState.NOT_DISCUSSED.value,
                CoverageState.PARTIAL.value,
                CoverageState.CLARIFY.value,
            }:
                seeds = {
                    "hypothesize": "When you take on new work, how do you decide what outcome you are testing for?",
                    "collaborate_research": "How do customer or stakeholder insights shape what you build next?",
                    "develop": "Walk us through how a change moves from idea into a pull request.",
                    "build": "What happens in your pipeline before a change is allowed to merge?",
                    "test_end_to_end": "How do you gain confidence beyond unit tests before release?",
                    "deploy": "How does a change get from a successful build into an environment users can reach?",
                    "verify": "After deployment, how do you confirm the change is healthy?",
                    "monitor": "What do you watch in production to know delivery is healthy?",
                    "respond": "Tell us about the last time a change misbehaved—how did you respond?",
                    "release": "How do you control when users actually receive a change?",
                    "measure": "How do you know a release created the value you intended?",
                    "learn": "How do learnings from releases feed the next cycle of work?",
                    "architect": "How do architectural and non-functional needs influence day-to-day delivery?",
                    "synthesize": "How do you turn research and options into a clear near-term plan?",
                    "stage": "What role do staging or pre-production environments play before production?",
                    "stabilize": "How do you limit blast radius when releasing risky changes?",
                }
                reason = f"Priority focus on unresolved practice '{key}' after recent discussion of {', '.join(matched) or 'general delivery'}."
                return seeds[key], reason
        return (
            "Is there anything about how you learn after a release that we have not covered yet?",
            "Remaining domain balance and learning loop.",
        )

    @staticmethod
    def _summary(answer: str) -> str:
        cleaned = re.sub(r"\s+", " ", answer).strip()
        if len(cleaned) <= 280:
            return cleaned or "No substantive answer provided."
        return cleaned[:277] + "…"

    @staticmethod
    def _claims(answer: str) -> list[str]:
        parts = [p.strip() for p in re.split(r"[.\n]", answer) if len(p.strip()) > 20]
        return parts[:6]
