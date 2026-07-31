from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.assessment_config.schema import DomainConfig, PracticeConfig
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.http import sanitize_remote_text
from app.models import Assessment, InterviewTurn
from app.models.ai_settings import InterviewSession
from app.models.enums import (
    AssessmentStatus,
    CoverageState,
    InterviewTurnSource,
    InterviewTurnType,
    StandardFindingStatus,
)
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
from app.services.enterprise_standards import EnterpriseStandardsService
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
        self.enterprise = EnterpriseStandardsService(db)

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

        # Immutable applicable-standard snapshots for this assessment interview.
        self.enterprise.snapshot_applicable(assessment_id)

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
        if analysis.standard_updates:
            self.enterprise.apply_standard_updates_from_analysis(
                assessment.id, analysis.standard_updates, turn_id=turn.id
            )
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
        # Host-facing summaries must never reveal enterprise statuses/findings.
        session.overall_coverage_summary = self._sanitize_host_narrative(
            analysis.overall_coverage_summary
        )
        session.last_telemetry_json = json.dumps(
            {**telemetry, "prompt_config_version": session.prompt_config_version}
        )
        session.provider_mode = provider.name

        if analysis.needs_immediate_clarification and analysis.clarification_question:
            session.pending_clarification = self._sanitize_host_narrative(
                analysis.clarification_question
            )
            session.last_outcome = "clarify"
            clarify_key = next(
                (
                    u.practice_key
                    for u in analysis.practice_updates
                    if u.coverage_state == CoverageState.CLARIFY
                ),
                None,
            )
            if clarify_key:
                try:
                    practice = self.model.require_practice(clarify_key)
                    domain = next(
                        d for d, p in self.model.ordered_practices() if p.key == practice.key
                    )
                    session.why_asking = self._sanitize_host_narrative(
                        self._why_with_practice_context(
                            practice,
                            domain,
                            "We need a bit more detail before this area can be marked covered.",
                        )
                    )
                    session.topic_label = f"{domain.short_name} · {practice.name}"
                except ValueError:
                    pass
        else:
            session.pending_clarification = None
            session.last_outcome = "sufficient"
            next_q = self._select_next_question(assessment, analysis)
            session.current_question = self._sanitize_host_narrative(next_q["question"])
            session.why_asking = self._sanitize_host_narrative(next_q["why"])
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
        if analysis.standard_updates:
            self.enterprise.apply_standard_updates_from_analysis(
                assessment.id, analysis.standard_updates, turn_id=turn.id
            )

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
        # Unknown standard keys are rejected; known keys sanitized.
        cleaned_standards = []
        for update in analysis.standard_updates:
            cleaned_standards.append(
                update.model_copy(
                    update={
                        "evidence_summary": sanitize_remote_text(
                            update.evidence_summary, max_len=4000
                        ),
                        "recommendation_candidate": sanitize_remote_text(
                            update.recommendation_candidate, max_len=4000
                        ),
                        "missing_evidence": [
                            sanitize_remote_text(m, max_len=400) for m in update.missing_evidence
                        ][:12],
                    }
                )
            )
        return analysis.model_copy(
            update={
                "practice_updates": cleaned_updates,
                "standard_updates": cleaned_standards,
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

    def _why_with_practice_context(
        self,
        practice: PracticeConfig,
        domain: DomainConfig,
        reason: str,
        *,
        extra_practices: list[PracticeConfig] | None = None,
    ) -> str:
        """Combine plain-language SAFe practice gloss with the facilitation reason."""
        blocks = [practice.participant_context.strip()]
        for extra in extra_practices or []:
            if extra.key == practice.key:
                continue
            text = (extra.participant_context or "").strip()
            if text and text not in blocks:
                blocks.append(text)
        reason_text = (reason or "").strip()
        if reason_text:
            blocks.append(reason_text)
        # domain unused for copy today but keeps call sites explicit about focus
        _ = domain
        return "\n\n".join(blocks)

    def _practice_question_payload(
        self,
        assessment: Assessment,
        practice: PracticeConfig,
        domain: DomainConfig,
        *,
        question: str,
        reason: str,
        evidence: str | None = None,
        extra_practices: list[PracticeConfig] | None = None,
    ) -> dict[str, str]:
        return {
            "question": question,
            "why": self._why_with_practice_context(
                practice, domain, reason, extra_practices=extra_practices
            ),
            "evidence": evidence if evidence is not None else self._evidence_blurb(assessment),
            "topic": f"{domain.short_name} · {practice.name}",
        }

    def _select_next_question(
        self, assessment: Assessment, analysis: InterviewAnalysisAI
    ) -> dict[str, str]:
        """Server-side next-best question selection; AI suggestion is advisory only.

        Optimizes for hidden SAFe practice coverage and applicable enterprise-standard
        coverage together. Prefers multi-coverage questions; never runs a separate
        enterprise questionnaire.
        """
        coverages = {c.practice_key: c for c in assessment.practice_coverages}
        # Priority 1: clarify states (immediate ambiguity)
        for domain, practice in self.model.ordered_practices():
            cov = coverages.get(practice.key)
            if cov and cov.coverage_state == CoverageState.CLARIFY.value:
                seed = (
                    practice.clarification_seeds[0].text
                    if practice.clarification_seeds
                    else analysis.next_best_question
                )
                return self._practice_question_payload(
                    assessment,
                    practice,
                    domain,
                    question=seed,
                    reason="We need clarity on this area before coverage can advance.",
                )
        # Priority 2: multi-coverage SAFe + enterprise (prefer simultaneous gathering)
        multi_q = self._select_multi_coverage_question(assessment, analysis)
        if multi_q is not None:
            return multi_q
        # Priority 3: contradictions
        for cov in assessment.practice_coverages:
            contras = json.loads(cov.contradictions_json or "[]")
            if contras:
                practice = self.model.require_practice(cov.practice_key)
                domain = next(d for d, p in self.model.ordered_practices() if p.key == practice.key)
                return self._practice_question_payload(
                    assessment,
                    practice,
                    domain,
                    question=practice.clarification_seeds[0].text,
                    reason="There is a tension between what the team said and observed tool evidence.",
                    evidence=contras[0],
                )
        # Priority 4: low confidence / partial (single-practice fallback)
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
            return self._practice_question_payload(
                assessment,
                practice,
                domain,
                question=practice.question_seeds[0].text,
                reason="This area was only partially covered and still has open gaps.",
            )
        # Priority 5: uncovered + domain balance
        touched_domains = {
            c.domain_key
            for c in assessment.practice_coverages
            if c.coverage_state != CoverageState.NOT_DISCUSSED.value
        }
        ordered = self.model.ordered_practices()
        for domain, practice in ordered:
            if domain.key not in touched_domains:
                cov = coverages.get(practice.key)
                if cov and cov.coverage_state == CoverageState.NOT_DISCUSSED.value:
                    return self._practice_question_payload(
                        assessment,
                        practice,
                        domain,
                        question=practice.question_seeds[0].text,
                        reason="Balancing coverage across SAFe DevOps domains.",
                    )
        for domain, practice in ordered:
            cov = coverages.get(practice.key)
            if cov and cov.coverage_state == CoverageState.NOT_DISCUSSED.value:
                return self._practice_question_payload(
                    assessment,
                    practice,
                    domain,
                    question=practice.question_seeds[0].text,
                    reason=analysis.reason_for_next_question
                    or "Continuing with uncovered delivery practices.",
                )
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
                "Optimize for remaining SAFe coverage and applicable enterprise-standard coverage together",
                "Prefer one question that gathers evidence for several SAFe practices and standards at once",
                "Do not ask enterprise standards as a separate questionnaire or one-by-one checklist",
                "Never invent standard keys; use only known_standard_keys",
                "Never mention enterprise-standard titles, statuses, or findings in facilitator-facing narratives",
                "human/tool contradictions",
                "missing evidence",
                "assessment fatigue and existing question count",
            ],
            **self.enterprise.interview_context_payload(assessment.id),
        }

    def _select_multi_coverage_question(
        self, assessment: Assessment, analysis: InterviewAnalysisAI
    ) -> dict[str, str] | None:
        """Prefer questions that advance several SAFe practices and open standards together.

        Host-facing copy stays neutral: no standard titles, statuses, or finding language.
        Caps how often multi-coverage prompts are injected so standards are not grilled one-by-one.
        """
        if self._multi_coverage_question_count(assessment.id) >= 3:
            return None

        open_findings = [
            f
            for f in self.enterprise.list_findings(assessment.id)
            if f.status
            in {
                StandardFindingStatus.INSUFFICIENT_EVIDENCE,
                StandardFindingStatus.FINDING,
                StandardFindingStatus.PARTIALLY_ALIGNED,
            }
        ]
        if not open_findings:
            return None

        coverages = {c.practice_key: c for c in assessment.practice_coverages}
        open_practice_keys = {
            key
            for key, cov in coverages.items()
            if cov.coverage_state
            in {
                CoverageState.NOT_DISCUSSED.value,
                CoverageState.PARTIAL.value,
                CoverageState.CLARIFY.value,
            }
        }
        if not open_practice_keys:
            return None

        # Score practice clusters by how many open standards they can also advance.
        best: dict[str, Any] | None = None
        best_score = 0
        for practice_key in open_practice_keys:
            related = [
                f for f in open_findings if practice_key in (f.mapped_practice_keys or [])
            ]
            if not related:
                continue
            related_practices = {
                pk
                for f in related
                for pk in (f.mapped_practice_keys or [])
                if pk in open_practice_keys
            }
            # Score: open practices in cluster + open standards touched (prefer multi).
            score = len(related_practices) + len(related)
            if score > best_score:
                best_score = score
                best = {
                    "anchor_practice": practice_key,
                    "practices": sorted(related_practices),
                    "findings": related,
                }

        # Require at least one open practice + one open standard; prefer score >= 3
        # (e.g. 2 practices + 1 standard, or 1 practice + 2 standards).
        if best is None or best_score < 2:
            return None
        # If only a single practice+standard pair remains and fatigue is high, skip.
        answered = self._answered_turn_count(assessment.id)
        if best_score == 2 and answered >= 10:
            return None

        anchor = self.model.require_practice(best["anchor_practice"])
        domain = next(d for d, p in self.model.ordered_practices() if p.key == anchor.key)
        guidance_bits: list[str] = []
        for finding in best["findings"][:3]:
            for snap in self.enterprise.list_snapshots(assessment.id):
                if snap.stable_key == finding.stable_key:
                    bit = (snap.definition.get("primary_interview_guidance") or "").strip()
                    if bit and bit not in guidance_bits:
                        guidance_bits.append(bit)
                    break

        practice_names = [
            self._practice_name(pk) for pk in best["practices"][:3]
        ]
        themes = self._neutral_themes_for_findings(best["findings"])

        # Prefer the model's multi-coverage suggestion when it already bridges topics.
        model_q = (analysis.next_best_question or "").strip()
        model_bridges = bool(model_q) and len(model_q) > 40 and (
            any(name.lower().split()[0] in model_q.lower() for name in practice_names)
            or any(
                theme.split()[0] in model_q.lower()
                for theme in themes
                if theme
            )
            or any(
                pk.replace("_", " ") in model_q.lower() for pk in best["practices"]
            )
        )

        if model_bridges and not self._contains_enterprise_leak(model_q):
            question = model_q
        else:
            seed = (
                guidance_bits[0]
                if guidance_bits
                else (
                    anchor.question_seeds[0].text
                    if anchor.question_seeds
                    else analysis.next_best_question
                )
            )
            extras = ""
            if len(guidance_bits) > 1:
                extras = " " + guidance_bits[1]
            elif len(best["practices"]) > 1:
                extras = (
                    f" Also cover how this connects to {practice_names[1]}"
                    + (f" and {practice_names[2]}" if len(practice_names) > 2 else "")
                    + "."
                )
            question = f"{self._evidence_blurb(assessment)}. {seed}{extras}".strip()

        why_reason = (
            "This helps us understand several delivery practices in one discussion"
            + (f", including useful context about your {' and '.join(themes)}" if themes else "")
            + "."
        )
        extras = [
            self.model.require_practice(pk)
            for pk in best["practices"][:3]
            if pk != anchor.key
        ]
        return self._practice_question_payload(
            assessment,
            anchor,
            domain,
            question=question[:4000],
            reason=why_reason,
            extra_practices=extras,
        )

    def _answered_turn_count(self, assessment_id: str) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(InterviewTurn)
                .where(
                    InterviewTurn.assessment_id == assessment_id,
                    InterviewTurn.answer_text.is_not(None),
                    InterviewTurn.answer_text != "",
                )
            )
            or 0
        )

    def _multi_coverage_question_count(self, assessment_id: str) -> int:
        """Count prior system questions that already probed platform/security themes."""
        turns = self.db.scalars(
            select(InterviewTurn).where(
                InterviewTurn.assessment_id == assessment_id,
                InterviewTurn.source == InterviewTurnSource.SYSTEM.value,
            )
        ).all()
        markers = (
            "credentials are provided",
            "secret",
            "quality gates",
            "platform",
            "observability",
            "approved deployment",
            "several delivery practices",
        )
        count = 0
        for turn in turns:
            text = (turn.question_text or "").lower()
            if any(m in text for m in markers):
                count += 1
        return count

    def _neutral_themes_for_findings(self, findings: list[Any]) -> list[str]:
        theme_by_category = {
            "security": "security practices",
            "platform": "platform practices",
            "delivery": "delivery practices",
            "operations": "operations practices",
        }
        themes: list[str] = []
        for finding in findings:
            category = (getattr(finding, "category", None) or "").strip().lower()
            theme = theme_by_category.get(category)
            if not theme:
                key = (getattr(finding, "stable_key", None) or "").lower()
                if "secret" in key or "security" in key:
                    theme = "security practices"
                elif "observ" in key or "monitor" in key:
                    theme = "operations practices"
                elif "runtime" in key or "openshift" in key or "platform" in key:
                    theme = "platform practices"
                else:
                    theme = "delivery practices"
            if theme not in themes:
                themes.append(theme)
        return themes[:3]

    def _contains_enterprise_leak(self, text: str) -> bool:
        lower = (text or "").lower()
        banned = (
            "enterprise standard",
            "enterprise standards",
            "enterprise alignment",
            "standard finding",
            "partially_aligned",
            "insufficient_evidence",
            "not_applicable",
            "alignment score",
        )
        return any(token in lower for token in banned)

    def _sanitize_host_narrative(self, text: str | None) -> str:
        """Remove enterprise statuses/findings language from host-visible strings."""
        if not text:
            return ""
        cleaned = sanitize_remote_text(text, max_len=4000)
        replacements = (
            ("enterprise standards", "platform and delivery practices"),
            ("enterprise standard", "platform practice"),
            ("enterprise alignment", "useful context"),
            ("standard finding", "observation"),
            ("partially_aligned", "discussed"),
            ("insufficient_evidence", "discussed"),
            ("not_applicable", "discussed"),
            ("alignment score", "progress"),
        )
        lower = cleaned
        for old, new in replacements:
            # Case-insensitive replace while preserving surrounding text.
            idx = lower.lower().find(old)
            while idx >= 0:
                lower = lower[:idx] + new + lower[idx + len(old) :]
                idx = lower.lower().find(old, idx + len(new))
        return lower

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
            text += (
                " One clarification will help: "
                + self._sanitize_host_narrative(analysis.clarification_question)
            )
        # Enterprise statuses/findings stay hidden; only neutral progress language.
        if analysis.standard_updates:
            themes = self._neutral_themes_for_standard_updates(analysis.standard_updates)
            if themes:
                text += (
                    " This also provided useful context about your "
                    + " and ".join(themes)
                    + "."
                )
            else:
                text += (
                    " This also provided useful context about your platform and security practices."
                )
        return self._sanitize_host_narrative(text)

    def _neutral_themes_for_standard_updates(self, updates: list[Any]) -> list[str]:
        theme_by_key = {
            "approved_secret_management": "security practices",
            "preferred_java_runtime_openshift": "platform practices",
            "pull_request_quality_gates": "delivery practices",
            "approved_deployment_automation": "delivery practices",
            "approved_production_observability": "operations practices",
        }
        themes: list[str] = []
        for update in updates:
            key = getattr(update, "standard_key", None) or ""
            theme = theme_by_key.get(key)
            if theme is None:
                lower = key.lower()
                if "secret" in lower or "security" in lower:
                    theme = "security practices"
                elif "observ" in lower or "monitor" in lower:
                    theme = "operations practices"
                elif "runtime" in lower or "openshift" in lower or "platform" in lower:
                    theme = "platform practices"
                else:
                    theme = "delivery practices"
            if theme not in themes:
                themes.append(theme)
        return themes[:3]

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
