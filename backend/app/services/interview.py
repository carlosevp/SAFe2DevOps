from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.http import sanitize_remote_text
from app.models import Assessment, InterviewTurn
from app.models.ai_settings import InterviewSession
from app.models.enums import AssessmentStatus, CoverageState, InterviewTurnSource, InterviewTurnType
from app.openai.factory import get_interview_provider
from app.repositories.assessment import AssessmentRepository
from app.schemas.interview import (
    CheckpointOut,
    InterviewAnalysisAI,
    InterviewSessionOut,
    InterviewTelemetryOut,
    PracticeCoveragePublic,
    TurnSubmitOut,
)
from app.services.ai_settings import AiSettingsService
from app.services.audit import AuditService
from app.services.evidence import EvidenceService
from app.services.lifecycle import LifecycleService
from app.services.storage import StorageService


class InterviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.assessments = AssessmentRepository(db)
        self.lifecycle = LifecycleService(db)
        self.audit = AuditService(db)
        self.evidence = EvidenceService(db)
        self.ai_settings = AiSettingsService(db)
        self.settings = get_settings()
        self.model = get_assessment_model_config()
        self.storage = StorageService(self.settings)

    def start(self, assessment_id: str, *, actor: str = "admin") -> InterviewSessionOut:
        assessment = self._require(assessment_id)
        status = AssessmentStatus(assessment.status)
        if status == AssessmentStatus.INTERVIEW_ACTIVE:
            return self.get_session(assessment_id)
        if status != AssessmentStatus.EVIDENCE_READY:
            raise AppError(
                code="interview_not_ready",
                message="Interview can start only from evidence_ready",
                status_code=409,
            )

        self.lifecycle.transition(
            assessment, AssessmentStatus.INTERVIEW_ACTIVE, actor_subject=actor
        )
        runtime = self.ai_settings.get()
        provider = get_interview_provider(self.db, self.settings)
        context = self._build_context(assessment)
        opening, telemetry = provider.generate_opening_question(context)

        session = self._get_or_create_session(assessment_id)
        session.interview_status = "active"
        session.current_question = opening.question_text
        session.why_asking = opening.why_asking
        session.evidence_context = opening.evidence_context
        session.topic_label = opening.topic_label
        session.pending_clarification = None
        session.draft_answer_text = ""
        session.last_outcome = "none"
        session.overall_coverage_summary = (
            "Interview started. Coverage updates appear after each answer."
        )
        session.coverage_confirmation = None
        session.prompt_config_version = self.ai_settings.prompt_config_version()
        session.model_name = runtime.assessment_model
        session.reasoning_effort = runtime.reasoning_effort
        session.provider_mode = provider.name
        session.last_telemetry_json = json.dumps(
            {**telemetry, "prompt_config_version": session.prompt_config_version}
        )
        session.answered_turn_count = 0
        session.paused_at = None
        self.db.flush()

        self._create_system_turn(
            assessment,
            question_text=opening.question_text,
            turn_type=InterviewTurnType.BROAD,
            idempotency_key=f"opening:{assessment_id}",
        )
        self.audit.record(
            assessment_id=assessment_id,
            event_type="interview.started",
            message="Adaptive interview started",
            actor_type="admin",
            actor_subject=actor,
            details={"provider": provider.name, "model": runtime.assessment_model},
        )
        return self.get_session(assessment_id)

    def resume(self, assessment_id: str, *, actor: str = "admin") -> InterviewSessionOut:
        assessment = self._require(assessment_id)
        status = AssessmentStatus(assessment.status)
        if status == AssessmentStatus.EVIDENCE_READY:
            return self.start(assessment_id, actor=actor)
        if status != AssessmentStatus.INTERVIEW_ACTIVE:
            raise AppError(
                code="interview_not_active", message="Interview is not active", status_code=409
            )
        session = self._require_session(assessment_id)
        session.interview_status = "active"
        session.paused_at = None
        self.db.flush()
        return self.get_session(assessment_id)

    def save_and_exit(
        self, assessment_id: str, *, draft: str | None = None, actor: str = "admin"
    ) -> InterviewSessionOut:
        session = self._require_session(assessment_id)
        if draft is not None:
            session.draft_answer_text = draft
        session.interview_status = "paused"
        session.paused_at = datetime.now(UTC)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="interview.paused",
            message="Interview saved and paused",
            actor_type="admin",
            actor_subject=actor,
        )
        self.db.flush()
        return self.get_session(assessment_id)

    def save_draft(self, assessment_id: str, draft_answer_text: str) -> InterviewSessionOut:
        session = self._require_session(assessment_id)
        session.draft_answer_text = draft_answer_text
        self.db.flush()
        return self.get_session(assessment_id)

    def submit_turn(
        self,
        assessment_id: str,
        *,
        answer_text: str,
        idempotency_key: str,
        is_clarification: bool = False,
        actor: str = "admin",
    ) -> TurnSubmitOut:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.INTERVIEW_ACTIVE:
            raise AppError(
                code="interview_not_active", message="Interview is not active", status_code=409
            )

        existing = self.db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.assessment_id == assessment_id,
                InterviewTurn.idempotency_key == idempotency_key,
            )
        )
        if existing is not None and existing.answer_text is not None:
            return TurnSubmitOut(
                session=self.get_session(assessment_id),
                analysis_summary="Duplicate submission",
                duplicated=True,
            )

        session = self._require_session(assessment_id)
        stop = self.model.stop_criteria
        if session.answered_turn_count >= stop.max_interview_turns:
            raise AppError(
                code="max_turns_reached", message="Maximum interview turns reached", status_code=409
            )

        if is_clarification and not session.pending_clarification:
            raise AppError(
                code="no_pending_clarification",
                message="No clarification is pending",
                status_code=400,
            )

        clean_answer = sanitize_remote_text(answer_text, max_len=20000).strip()
        if not clean_answer:
            raise AppError(code="empty_answer", message="Answer text is required", status_code=400)

        provider = get_interview_provider(self.db, self.settings)
        context = self._build_context(assessment)
        context.update(
            {
                "answer_text": clean_answer,
                "is_clarification": is_clarification,
                "pending_clarification": session.pending_clarification,
                "recent_questions": [session.current_question],
            }
        )

        try:
            analysis, telemetry = provider.analyze_answer(context)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                code="interview_analysis_failed",
                message="Failed to analyze answer",
                status_code=502,
                details={"error_type": type(exc).__name__},
            ) from exc

        analysis = self._validate_and_sanitize_analysis(analysis)
        analysis_ref = self._persist_analysis(assessment_id, analysis, telemetry)

        question_text = (
            session.pending_clarification if is_clarification else session.current_question
        )
        turn = InterviewTurn(
            assessment_id=assessment_id,
            sequence=self._next_sequence(assessment_id),
            turn_type=InterviewTurnType.CLARIFICATION.value
            if is_clarification
            else InterviewTurnType.BROAD.value,
            source=InterviewTurnSource.ROOM_TYPED.value,
            question_text=question_text,
            answer_text=clean_answer,
            practice_keys_json=json.dumps([u.practice_key for u in analysis.practice_updates]),
            structured_analysis_ref=analysis_ref,
            idempotency_key=idempotency_key,
            content_trust="untrusted",
        )
        self.db.add(turn)
        self.db.flush()

        self._apply_practice_updates(assessment, analysis, turn_id=turn.id)
        confirmation = self._coverage_confirmation(analysis)

        # Clarification rounds cap
        if analysis.needs_immediate_clarification and analysis.clarification_question:
            for update in analysis.practice_updates:
                if update.coverage_state == CoverageState.CLARIFY:
                    rounds = self._clarification_rounds(assessment_id, update.practice_key)
                    if rounds >= self.model.stop_criteria.max_clarification_rounds_per_practice:
                        analysis.needs_immediate_clarification = False
                        analysis.clarification_question = None
                        break

        session.answered_turn_count += 1
        session.draft_answer_text = ""
        session.last_analysis_ref = analysis_ref
        session.coverage_confirmation = confirmation
        session.overall_coverage_summary = analysis.overall_coverage_summary
        session.last_telemetry_json = json.dumps(
            {**telemetry, "prompt_config_version": session.prompt_config_version}
        )
        session.provider_mode = provider.name

        if analysis.needs_immediate_clarification and analysis.clarification_question:
            session.pending_clarification = analysis.clarification_question
            session.last_outcome = "clarify"
        else:
            session.pending_clarification = None
            session.last_outcome = "sufficient"
            next_q = self._select_next_question(assessment, analysis)
            session.current_question = next_q["question"]
            session.why_asking = next_q["why"]
            session.evidence_context = next_q["evidence"]
            session.topic_label = next_q["topic"]
            self._create_system_turn(
                assessment,
                question_text=session.current_question,
                turn_type=InterviewTurnType.FOLLOW_UP,
                idempotency_key=f"next:{assessment_id}:{session.answered_turn_count}",
            )

        self.audit.record(
            assessment_id=assessment_id,
            event_type="interview.turn_submitted",
            message="Interview turn analyzed",
            actor_type="admin",
            actor_subject=actor,
            details={
                "turn_id": turn.id,
                "practice_keys": [u.practice_key for u in analysis.practice_updates],
                "outcome": session.last_outcome,
                "provider": provider.name,
                "latency_ms": telemetry.get("latency_ms"),
                "input_tokens": telemetry.get("input_tokens"),
                "output_tokens": telemetry.get("output_tokens"),
            },
        )
        self.db.flush()

        covered = [
            self._practice_name(u.practice_key)
            for u in analysis.practice_updates
            if u.coverage_state == CoverageState.SUFFICIENT
        ]
        partial = [
            self._practice_name(u.practice_key)
            for u in analysis.practice_updates
            if u.coverage_state == CoverageState.PARTIAL
        ]
        clarify = [
            self._practice_name(u.practice_key)
            for u in analysis.practice_updates
            if u.coverage_state == CoverageState.CLARIFY
        ]
        return TurnSubmitOut(
            session=self.get_session(assessment_id),
            analysis_summary=analysis.response_summary,
            claims=analysis.claims,
            covered_practices=covered,
            partial_practices=partial,
            clarify_practices=clarify,
            duplicated=False,
        )

    def ingest_remote_contribution(
        self,
        assessment_id: str,
        *,
        answer_text: str,
        question_text: str,
        idempotency_key: str,
        actor: str = "admin",
    ) -> dict[str, Any]:
        """Analyze a remote contribution without advancing the host interview screen."""
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.INTERVIEW_ACTIVE:
            raise AppError(
                code="interview_not_active", message="Interview is not active", status_code=409
            )

        existing = self.db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.assessment_id == assessment_id,
                InterviewTurn.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            practice_names = [
                self._practice_name(k) for k in json.loads(existing.practice_keys_json or "[]")
            ]
            return {
                "turn_id": existing.id,
                "affected_practices": practice_names,
                "duplicated": True,
                "host_question_unchanged": True,
            }

        session = self._require_session(assessment_id)
        # Snapshot host screen so remote inclusion cannot mutate it.
        frozen_question = session.current_question
        frozen_why = session.why_asking
        frozen_evidence = session.evidence_context
        frozen_topic = session.topic_label
        frozen_pending = session.pending_clarification
        frozen_draft = session.draft_answer_text
        frozen_outcome = session.last_outcome

        clean_answer = sanitize_remote_text(answer_text, max_len=20000).strip()
        if not clean_answer:
            raise AppError(code="empty_answer", message="Answer text is required", status_code=400)

        provider = get_interview_provider(self.db, self.settings)
        context = self._build_context(assessment)
        context.update(
            {
                "answer_text": clean_answer,
                "is_clarification": False,
                "pending_clarification": None,
                "recent_questions": [question_text or frozen_question],
            }
        )
        try:
            analysis, telemetry = provider.analyze_answer(context)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                code="interview_analysis_failed",
                message="Failed to analyze remote contribution",
                status_code=502,
                details={"error_type": type(exc).__name__},
            ) from exc

        analysis = self._validate_and_sanitize_analysis(analysis)
        analysis_ref = self._persist_analysis(assessment_id, analysis, telemetry)
        turn = InterviewTurn(
            assessment_id=assessment_id,
            sequence=self._next_sequence(assessment_id),
            turn_type=InterviewTurnType.BROAD.value,
            source=InterviewTurnSource.REMOTE_CONTRIBUTION.value,
            question_text=sanitize_remote_text(question_text or frozen_question, max_len=4000),
            answer_text=clean_answer,
            practice_keys_json=json.dumps([u.practice_key for u in analysis.practice_updates]),
            structured_analysis_ref=analysis_ref,
            idempotency_key=idempotency_key,
            content_trust="untrusted",
        )
        self.db.add(turn)
        self.db.flush()
        self._apply_practice_updates(assessment, analysis, turn_id=turn.id)

        # Restore host screen fields — remote include must not advance the workshop.
        session.current_question = frozen_question
        session.why_asking = frozen_why
        session.evidence_context = frozen_evidence
        session.topic_label = frozen_topic
        session.pending_clarification = frozen_pending
        session.draft_answer_text = frozen_draft
        session.last_outcome = frozen_outcome
        session.last_analysis_ref = analysis_ref
        session.last_telemetry_json = json.dumps(
            {
                **telemetry,
                "prompt_config_version": session.prompt_config_version,
                "source": "remote_contribution",
            }
        )
        self.db.flush()

        affected = [self._practice_name(u.practice_key) for u in analysis.practice_updates]
        self.audit.record(
            assessment_id=assessment_id,
            event_type="interview.remote_contribution_ingested",
            message="Remote contribution analyzed without advancing host screen",
            actor_type="admin",
            actor_subject=actor,
            details={
                "turn_id": turn.id,
                "practice_keys": [u.practice_key for u in analysis.practice_updates],
            },
        )
        return {
            "turn_id": turn.id,
            "affected_practices": affected,
            "duplicated": False,
            "host_question_unchanged": True,
            "analysis_summary": analysis.response_summary,
        }

    def checkpoint(self, assessment_id: str) -> CheckpointOut:
        assessment = self._require(assessment_id)
        practices = self._public_practices(assessment)
        sufficient = [p for p in practices if p.coverage_state == CoverageState.SUFFICIENT]
        partial = [p for p in practices if p.coverage_state == CoverageState.PARTIAL]
        not_discussed = [p for p in practices if p.coverage_state == CoverageState.NOT_DISCUSSED]
        clarify = [p for p in practices if p.coverage_state == CoverageState.CLARIFY]
        eligible, blockers = self.compute_completion_eligibility(assessment)
        remaining = partial + clarify + not_discussed
        return CheckpointOut(
            assessment_id=assessment_id,
            headline="You've covered a meaningful share of the delivery pipeline."
            if len(sufficient) >= 8
            else "Good progress — several delivery topics still need discussion.",
            summary=(
                f"{len(sufficient)} of 16 practices sufficiently covered · "
                f"{len(partial)} partially covered · {len(not_discussed)} not yet discussed"
            ),
            sufficient_count=len(sufficient),
            partial_count=len(partial),
            not_discussed_count=len(not_discussed),
            clarify_count=len(clarify),
            covered=[{"label": p.practice_name, "domain": p.domain_short_name} for p in sufficient],
            remaining=[
                {
                    "label": p.practice_name,
                    "domain": p.domain_short_name,
                    "priority": "high" if p.coverage_state == CoverageState.CLARIFY else "medium",
                }
                for p in remaining
            ],
            completion_eligible=eligible,
            completion_blockers=blockers,
            impact_note=(
                "Finishing now is allowed only when server-side completion criteria are met. "
                "AI recommendations alone cannot end the assessment."
            ),
        )

    def complete(self, assessment_id: str, *, actor: str = "admin") -> InterviewSessionOut:
        assessment = self._require(assessment_id)
        if AssessmentStatus(assessment.status) != AssessmentStatus.INTERVIEW_ACTIVE:
            raise AppError(
                code="interview_not_active", message="Interview is not active", status_code=409
            )
        eligible, blockers = self.compute_completion_eligibility(assessment)
        if not eligible:
            raise AppError(
                code="completion_criteria_unmet",
                message="Interview completion criteria are not met",
                status_code=409,
                details={"blockers": blockers},
            )
        self.lifecycle.transition(
            assessment, AssessmentStatus.INTERVIEW_COMPLETE, actor_subject=actor
        )
        session = self._require_session(assessment_id)
        session.interview_status = "complete"
        self.db.flush()
        return self.get_session(assessment_id)

    def get_session(self, assessment_id: str) -> InterviewSessionOut:
        assessment = self._require(assessment_id)
        session = self._require_session(assessment_id)
        eligible, blockers = self.compute_completion_eligibility(assessment)
        telemetry_raw = json.loads(session.last_telemetry_json or "{}")
        telemetry = InterviewTelemetryOut(
            provider=session.provider_mode,
            model=session.model_name,
            reasoning_effort=session.reasoning_effort,
            latency_ms=telemetry_raw.get("latency_ms"),
            input_tokens=telemetry_raw.get("input_tokens"),
            output_tokens=telemetry_raw.get("output_tokens"),
            prompt_config_version=session.prompt_config_version,
        )
        return InterviewSessionOut(
            assessment_id=assessment.id,
            team_name=assessment.team_name,
            product_service_name=assessment.product_service_name,
            status=assessment.status,
            interview_status=session.interview_status,
            current_question=session.current_question,
            why_asking=session.why_asking,
            evidence_context=session.evidence_context,
            topic_label=session.topic_label,
            pending_clarification=session.pending_clarification,
            draft_answer_text=session.draft_answer_text,
            last_outcome=session.last_outcome,  # type: ignore[arg-type]
            overall_coverage_summary=session.overall_coverage_summary,
            coverage_confirmation=session.coverage_confirmation,
            turn_count=session.answered_turn_count,
            answered_turn_count=session.answered_turn_count,
            completion_eligible=eligible,
            completion_blockers=blockers,
            practices=self._public_practices(assessment),
            telemetry=telemetry,
        )

    def compute_completion_eligibility(self, assessment: Assessment) -> tuple[bool, list[str]]:
        stop = self.model.stop_criteria
        blockers: list[str] = []
        coverages = list(assessment.practice_coverages)
        sufficient = [c for c in coverages if c.coverage_state == CoverageState.SUFFICIENT.value]
        if len(sufficient) < stop.min_practices_with_sufficient_coverage:
            blockers.append(
                f"Need {stop.min_practices_with_sufficient_coverage} sufficiently covered practices "
                f"(have {len(sufficient)})"
            )
        if stop.require_all_domains_touched:
            touched_domains = {
                c.domain_key
                for c in coverages
                if c.coverage_state != CoverageState.NOT_DISCUSSED.value
            }
            all_domains = {d.key for d in self.model.domains}
            missing = sorted(all_domains - touched_domains)
            if missing:
                blockers.append(f"Domains not yet discussed: {', '.join(missing)}")
        confidences = [c.confidence for c in coverages if c.confidence is not None]
        if confidences:
            overall = sum(confidences) / len(confidences)
            if overall < stop.min_overall_confidence:
                blockers.append(
                    f"Overall confidence {overall:.2f} below {stop.min_overall_confidence:.2f}"
                )
        clarify_open = [c for c in coverages if c.coverage_state == CoverageState.CLARIFY.value]
        if clarify_open:
            blockers.append(f"{len(clarify_open)} practice(s) still need clarification")
        return (len(blockers) == 0, blockers)

    def _validate_and_sanitize_analysis(self, analysis: InterviewAnalysisAI) -> InterviewAnalysisAI:
        known = self.model.practice_keys()
        cleaned_updates = []
        for update in analysis.practice_updates:
            if update.practice_key not in known:
                raise AppError(
                    code="unknown_practice_key",
                    message=f"Model returned unknown practice key: {update.practice_key}",
                    status_code=502,
                    details={"practice_key": update.practice_key},
                )
            # Never allow narrative fields to smuggle scores to the UI layer.
            summary = update.evidence_summary
            for banned in ("score", "maturity level", "rated as"):
                summary = summary.replace(banned, "").replace(banned.title(), "")
            cleaned_updates.append(
                update.model_copy(
                    update={
                        "evidence_summary": sanitize_remote_text(summary, max_len=2000),
                        "open_gaps": [
                            sanitize_remote_text(g, max_len=400) for g in update.open_gaps
                        ][:12],
                        "contradictions": [
                            sanitize_remote_text(c, max_len=400) for c in update.contradictions
                        ][:12],
                    }
                )
            )
        if analysis.needs_immediate_clarification and not analysis.clarification_question:
            raise AppError(
                code="invalid_analysis_output",
                message="Clarification requested without a clarification question",
                status_code=502,
            )
        return analysis.model_copy(
            update={
                "practice_updates": cleaned_updates,
                "response_summary": sanitize_remote_text(analysis.response_summary, max_len=4000),
                "overall_coverage_summary": sanitize_remote_text(
                    analysis.overall_coverage_summary, max_len=4000
                ),
                "next_best_question": sanitize_remote_text(
                    analysis.next_best_question, max_len=4000
                ),
                "clarification_question": (
                    sanitize_remote_text(analysis.clarification_question, max_len=2000)
                    if analysis.clarification_question
                    else None
                ),
                "claims": [sanitize_remote_text(c, max_len=500) for c in analysis.claims][:12],
                "open_gaps": [sanitize_remote_text(g, max_len=400) for g in analysis.open_gaps][
                    :20
                ],
                "contradictions": [
                    sanitize_remote_text(c, max_len=400) for c in analysis.contradictions
                ][:20],
            }
        )

    def _apply_practice_updates(
        self, assessment: Assessment, analysis: InterviewAnalysisAI, *, turn_id: str
    ) -> None:
        by_key = {c.practice_key: c for c in assessment.practice_coverages}
        for update in analysis.practice_updates:
            coverage = by_key.get(update.practice_key)
            if coverage is None:
                continue
            # Monotonic-ish: don't regress sufficient to not_discussed.
            current = CoverageState(coverage.coverage_state)
            incoming = update.coverage_state
            if current == CoverageState.SUFFICIENT and incoming == CoverageState.NOT_DISCUSSED:
                incoming = CoverageState.SUFFICIENT
            coverage.coverage_state = incoming.value
            coverage.confidence = update.confidence
            # Candidate scores stored for admin review only — never exposed in interview APIs.
            if update.candidate_score is not None:
                coverage.ai_candidate_score = update.candidate_score
            summaries = json.loads(coverage.evidence_summaries_json or "[]")
            if update.evidence_summary:
                summaries.append(update.evidence_summary)
            coverage.evidence_summaries_json = json.dumps(summaries[-20:])
            turn_ids = json.loads(coverage.source_turn_ids_json or "[]")
            turn_ids.append(turn_id)
            coverage.source_turn_ids_json = json.dumps(turn_ids[-50:])
            gaps = json.loads(coverage.open_gaps_json or "[]")
            for gap in update.open_gaps:
                if gap not in gaps:
                    gaps.append(gap)
            coverage.open_gaps_json = json.dumps(gaps[-20:])
            contras = json.loads(coverage.contradictions_json or "[]")
            for item in update.contradictions:
                if item not in contras:
                    contras.append(item)
            coverage.contradictions_json = json.dumps(contras[-20:])
        self.db.flush()

    def _select_next_question(
        self, assessment: Assessment, analysis: InterviewAnalysisAI
    ) -> dict[str, str]:
        """Server-side next-best question selection; AI suggestion is advisory only."""
        coverages = {c.practice_key: c for c in assessment.practice_coverages}
        # Priority 1: clarify states
        for domain, practice in self.model.ordered_practices():
            cov = coverages.get(practice.key)
            if cov and cov.coverage_state == CoverageState.CLARIFY.value:
                seed = (
                    practice.clarification_seeds[0].text
                    if practice.clarification_seeds
                    else analysis.next_best_question
                )
                return {
                    "question": seed,
                    "why": f"We need clarity on {practice.name} before coverage can advance.",
                    "evidence": self._evidence_blurb(assessment),
                    "topic": domain.short_name,
                }
        # Priority 2: low confidence / partial
        low = sorted(
            [
                c
                for c in assessment.practice_coverages
                if c.coverage_state == CoverageState.PARTIAL.value
            ],
            key=lambda c: c.confidence or 0.0,
        )
        if low:
            practice = self.model.require_practice(low[0].practice_key)
            domain = next(d for d, p in self.model.ordered_practices() if p.key == practice.key)
            return {
                "question": practice.question_seeds[0].text,
                "why": "This practice was only partially covered and still has open gaps.",
                "evidence": self._evidence_blurb(assessment),
                "topic": domain.short_name,
            }
        # Priority 3: contradictions
        for cov in assessment.practice_coverages:
            contras = json.loads(cov.contradictions_json or "[]")
            if contras:
                practice = self.model.require_practice(cov.practice_key)
                domain = next(d for d, p in self.model.ordered_practices() if p.key == practice.key)
                return {
                    "question": practice.clarification_seeds[0].text,
                    "why": "There is a tension between what the team said and observed tool evidence.",
                    "evidence": contras[0],
                    "topic": domain.short_name,
                }
        # Priority 4/6: uncovered + domain balance
        touched_domains = {
            c.domain_key
            for c in assessment.practice_coverages
            if c.coverage_state != CoverageState.NOT_DISCUSSED.value
        }
        ordered = self.model.ordered_practices()
        # Prefer domains not yet touched.
        for domain, practice in ordered:
            if domain.key not in touched_domains:
                cov = coverages.get(practice.key)
                if cov and cov.coverage_state == CoverageState.NOT_DISCUSSED.value:
                    return {
                        "question": practice.question_seeds[0].text,
                        "why": "Balancing coverage across SAFe DevOps domains.",
                        "evidence": self._evidence_blurb(assessment),
                        "topic": domain.short_name,
                    }
        for domain, practice in ordered:
            cov = coverages.get(practice.key)
            if cov and cov.coverage_state == CoverageState.NOT_DISCUSSED.value:
                return {
                    "question": practice.question_seeds[0].text,
                    "why": analysis.reason_for_next_question
                    or "Continuing with uncovered delivery practices.",
                    "evidence": self._evidence_blurb(assessment),
                    "topic": domain.short_name,
                }
        # Fall back to model suggestion (sanitized).
        return {
            "question": analysis.next_best_question,
            "why": analysis.reason_for_next_question,
            "evidence": self._evidence_blurb(assessment),
            "topic": "Follow-up",
        }

    def _build_context(self, assessment: Assessment) -> dict[str, Any]:
        selection = assessment.source_selection
        snapshot = self.evidence.get_latest_snapshot(assessment.id)
        metrics = []
        tool_signals: dict[str, Any] = {}
        if snapshot:
            for metric in snapshot.metrics[:12]:
                metrics.append(f"{metric.label}: {metric.value_text}")
                if metric.key == "ado_pipeline_success" and metric.value_numeric is not None:
                    tool_signals["pipeline_success_rate"] = metric.value_numeric
        evidence_summary = (
            "; ".join(metrics) if metrics else "No normalized evidence metrics available."
        )
        return {
            "team_name": assessment.team_name,
            "product_service_name": assessment.product_service_name,
            "jira_project_key": selection.jira_project_key if selection else None,
            "ado_repository_name": selection.ado_repository_name if selection else None,
            "lookback_days": assessment.lookback_days,
            "evidence_summary": evidence_summary,
            "influence_mode": assessment.evidence_influence_mode,
            "known_practice_keys": sorted(self.model.practice_keys()),
            "coverage_states": {
                c.practice_key: c.coverage_state for c in assessment.practice_coverages
            },
            "tool_signals": tool_signals,
            "required_dimensions": list(self.model.required_evaluation_dimensions),
            "question_priority_guidance": [
                "uncovered required rubric dimensions",
                "low-confidence practices",
                "human/tool contradictions",
                "questions covering several practices",
                "context from most recent answer",
                "remaining domain balance",
            ],
        }

    def _evidence_blurb(self, assessment: Assessment) -> str:
        snapshot = self.evidence.get_latest_snapshot(assessment.id)
        if snapshot is None:
            return "Evidence snapshot not available."
        bits = [f"{m.label} {m.value_text}" for m in snapshot.metrics[:4]]
        return (
            f"{snapshot.jira_project_key} / {snapshot.ado_repository_name} · "
            f"last {snapshot.lookback_days} days · " + "; ".join(bits)
        )

    def _coverage_confirmation(self, analysis: InterviewAnalysisAI) -> str:
        covered = [
            self._practice_name(u.practice_key)
            for u in analysis.practice_updates
            if u.coverage_state == CoverageState.SUFFICIENT
        ]
        partial = [
            self._practice_name(u.practice_key)
            for u in analysis.practice_updates
            if u.coverage_state == CoverageState.PARTIAL
        ]
        clarify = [
            self._practice_name(u.practice_key)
            for u in analysis.practice_updates
            if u.coverage_state == CoverageState.CLARIFY
        ]
        parts: list[str] = []
        if covered:
            parts.append(f"This covered {', '.join(covered)}")
        if partial:
            parts.append(f"partially covered {', '.join(partial)}")
        text = ", and ".join(parts) + "." if parts else "Limited new coverage from this answer."
        if clarify and analysis.clarification_question:
            text += f" One clarification will help: {analysis.clarification_question}"
        return text

    def _practice_name(self, key: str) -> str:
        try:
            return self.model.require_practice(key).name
        except ValueError:
            return key.replace("_", " ").title()

    def _public_practices(self, assessment: Assessment) -> list[PracticeCoveragePublic]:
        domain_short = {d.key: d.short_name for d in self.model.domains}
        name_by_key = {p.key: p.name for _, p in self.model.ordered_practices()}
        domain_by_key = {p.key: d.key for d, p in self.model.ordered_practices()}
        out: list[PracticeCoveragePublic] = []
        for coverage in sorted(assessment.practice_coverages, key=lambda c: c.practice_key):
            domain_key = coverage.domain_key or domain_by_key.get(coverage.practice_key, "")
            out.append(
                PracticeCoveragePublic(
                    practice_key=coverage.practice_key,
                    practice_name=name_by_key.get(coverage.practice_key, coverage.practice_key),
                    domain_key=domain_key,
                    domain_short_name=domain_short.get(domain_key, domain_key),
                    coverage_state=CoverageState(coverage.coverage_state),
                    open_gaps=json.loads(coverage.open_gaps_json or "[]"),
                )
            )
        return out

    def _persist_analysis(
        self, assessment_id: str, analysis: InterviewAnalysisAI, telemetry: dict[str, Any]
    ) -> str:
        root = self.storage.ensure_directories().working / "interview" / assessment_id
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "analysis": analysis.model_dump(mode="json"),
            "telemetry": {
                "provider": telemetry.get("provider"),
                "model": telemetry.get("model"),
                "reasoning_effort": telemetry.get("reasoning_effort"),
                "latency_ms": telemetry.get("latency_ms"),
                "input_tokens": telemetry.get("input_tokens"),
                "output_tokens": telemetry.get("output_tokens"),
            },
            "stored_at": datetime.now(UTC).isoformat(),
        }
        # Strip nothing sensitive from answers here — answers live on InterviewTurn; analysis summaries only.
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        name = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{len(raw)}.json.gz"
        path = root / name
        with gzip.open(path, "wb") as handle:
            handle.write(raw)
        return f"working/interview/{assessment_id}/{name}"

    def _create_system_turn(
        self,
        assessment: Assessment,
        *,
        question_text: str,
        turn_type: InterviewTurnType,
        idempotency_key: str,
    ) -> InterviewTurn | None:
        existing = self.db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.assessment_id == assessment.id,
                InterviewTurn.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing
        turn = InterviewTurn(
            assessment_id=assessment.id,
            sequence=self._next_sequence(assessment.id),
            turn_type=turn_type.value,
            source=InterviewTurnSource.SYSTEM.value,
            question_text=question_text,
            answer_text=None,
            practice_keys_json="[]",
            idempotency_key=idempotency_key,
            content_trust="system",
        )
        self.db.add(turn)
        self.db.flush()
        return turn

    def _next_sequence(self, assessment_id: str) -> int:
        current = self.db.scalar(
            select(InterviewTurn.sequence)
            .where(InterviewTurn.assessment_id == assessment_id)
            .order_by(InterviewTurn.sequence.desc())
            .limit(1)
        )
        return int(current or 0) + 1

    def _clarification_rounds(self, assessment_id: str, practice_key: str) -> int:
        turns = self.db.scalars(
            select(InterviewTurn).where(
                InterviewTurn.assessment_id == assessment_id,
                InterviewTurn.turn_type == InterviewTurnType.CLARIFICATION.value,
            )
        ).all()
        count = 0
        for turn in turns:
            keys = json.loads(turn.practice_keys_json or "[]")
            if practice_key in keys:
                count += 1
        return count

    def _get_or_create_session(self, assessment_id: str) -> InterviewSession:
        session = self.db.scalar(
            select(InterviewSession).where(InterviewSession.assessment_id == assessment_id)
        )
        if session is None:
            session = InterviewSession(assessment_id=assessment_id)
            self.db.add(session)
            self.db.flush()
        return session

    def _require_session(self, assessment_id: str) -> InterviewSession:
        session = self.db.scalar(
            select(InterviewSession).where(InterviewSession.assessment_id == assessment_id)
        )
        if session is None:
            raise AppError(
                code="interview_session_missing",
                message="Interview session not found",
                status_code=404,
            )
        return session

    def _require(self, assessment_id: str) -> Assessment:
        assessment = self.db.scalar(
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.practice_coverages),
                selectinload(Assessment.source_selection),
                selectinload(Assessment.interview_turns),
            )
        )
        if assessment is None:
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return assessment
