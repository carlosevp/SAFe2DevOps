from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.assessment_config import get_assessment_model_config
from app.core.errors import AppError
from app.integrations.http import sanitize_remote_text
from app.models import (
    Assessment,
    AssessmentStandardFinding,
    AssessmentStandardSnapshot,
    AssessmentTechnologyContext,
    EnterpriseStandard,
    EnterpriseStandardCondition,
)
from app.models.enums import (
    APPLICABILITY_FIELDS,
    ApplicabilityMode,
    AssessmentStatus,
    ConditionLogicalGroup,
    ConditionOperator,
    RequirementLevel,
    StandardFindingStatus,
)
from app.schemas.enterprise import (
    EnterpriseStandardIn,
    EnterpriseStandardOut,
    EnterpriseStandardUpdate,
    StandardConditionIn,
    StandardConditionOut,
    StandardFindingOut,
    StandardFindingUpdateIn,
    StandardSnapshotOut,
    TechnologyContextIn,
    TechnologyContextOut,
)
from app.services.audit import AuditService

SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class EnterpriseStandardsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.model = get_assessment_model_config()

    # ── library CRUD ──────────────────────────────────────────────────────────

    def list_standards(
        self,
        *,
        search: str | None = None,
        category: str | None = None,
        active: bool | None = None,
    ) -> list[EnterpriseStandardOut]:
        stmt = select(EnterpriseStandard).options(selectinload(EnterpriseStandard.conditions))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    EnterpriseStandard.title.ilike(like),
                    EnterpriseStandard.stable_key.ilike(like),
                    EnterpriseStandard.category.ilike(like),
                )
            )
        if category:
            stmt = stmt.where(EnterpriseStandard.category == category)
        if active is not None:
            stmt = stmt.where(EnterpriseStandard.active.is_(active))
        stmt = stmt.order_by(EnterpriseStandard.display_order, EnterpriseStandard.title)
        return [self._to_out(row) for row in self.db.scalars(stmt).all()]

    def get_standard(self, standard_id: str) -> EnterpriseStandardOut:
        return self._to_out(self._require_standard(standard_id))

    def create_standard(self, body: EnterpriseStandardIn, *, actor: str) -> EnterpriseStandardOut:
        self._validate_payload(body)
        if self.db.scalar(
            select(EnterpriseStandard).where(EnterpriseStandard.stable_key == body.stable_key)
        ):
            raise AppError(
                code="duplicate_stable_key", message="stable_key already exists", status_code=409
            )
        row = EnterpriseStandard(
            stable_key=body.stable_key,
            title=body.title.strip(),
            category=body.category.strip(),
            description=body.description.strip(),
            requirement_level=body.requirement_level.value,
            active=body.active,
            applicability_mode=body.applicability_mode.value,
            mapped_practice_keys_json=json.dumps(body.mapped_practice_keys),
            primary_interview_guidance=body.primary_interview_guidance.strip(),
            follow_up_guidance=body.follow_up_guidance.strip(),
            evidence_expectations=body.evidence_expectations.strip(),
            recommendation_when_unmet=body.recommendation_when_unmet.strip(),
            display_order=body.display_order,
        )
        self.db.add(row)
        self.db.flush()
        self._replace_conditions(row, body.conditions)
        self.audit.record(
            assessment_id=None,
            event_type="enterprise_standard.created",
            message=f"Created standard {row.stable_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"standard_id": row.id, "stable_key": row.stable_key},
        )
        self.db.flush()
        return self._to_out(row)

    def update_standard(
        self, standard_id: str, body: EnterpriseStandardUpdate, *, actor: str
    ) -> EnterpriseStandardOut:
        row = self._require_standard(standard_id)
        data = body.model_dump(exclude_unset=True)
        if "mapped_practice_keys" in data:
            self._validate_practice_keys(data["mapped_practice_keys"] or [])
            row.mapped_practice_keys_json = json.dumps(data.pop("mapped_practice_keys") or [])
        if "conditions" in data:
            conditions = data.pop("conditions") or []
            if row.applicability_mode == ApplicabilityMode.CONDITIONS.value or (
                data.get("applicability_mode") == ApplicabilityMode.CONDITIONS
            ):
                pass
            self._replace_conditions(
                row,
                [
                    StandardConditionIn.model_validate(c) if isinstance(c, dict) else c
                    for c in conditions
                ],
            )
        for key, value in data.items():
            if key in {"requirement_level", "applicability_mode"} and value is not None:
                setattr(row, key, value.value if hasattr(value, "value") else value)
            elif value is not None and hasattr(row, key):
                setattr(row, key, value.strip() if isinstance(value, str) else value)
        if row.applicability_mode == ApplicabilityMode.CONDITIONS.value and not row.conditions:
            raise AppError(
                code="conditions_required",
                message="Conditional standards require at least one applicability rule",
                status_code=400,
            )
        self.audit.record(
            assessment_id=None,
            event_type="enterprise_standard.updated",
            message=f"Updated standard {row.stable_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"standard_id": row.id},
        )
        self.db.flush()
        return self._to_out(row)

    def set_active(self, standard_id: str, *, active: bool, actor: str) -> EnterpriseStandardOut:
        row = self._require_standard(standard_id)
        row.active = active
        self.audit.record(
            assessment_id=None,
            event_type="enterprise_standard.toggled",
            message=f"{'Activated' if active else 'Deactivated'} standard {row.stable_key}",
            actor_type="admin",
            actor_subject=actor,
            details={"standard_id": row.id, "active": active},
        )
        self.db.flush()
        return self._to_out(row)

    def duplicate(self, standard_id: str, *, actor: str) -> EnterpriseStandardOut:
        source = self._require_standard(standard_id)
        base = f"{source.stable_key}_copy"
        key = base
        n = 2
        while self.db.scalar(
            select(EnterpriseStandard).where(EnterpriseStandard.stable_key == key)
        ):
            key = f"{base}_{n}"
            n += 1
        payload = EnterpriseStandardIn(
            stable_key=key,
            title=f"{source.title} (copy)",
            category=source.category,
            description=source.description,
            requirement_level=RequirementLevel(source.requirement_level),
            active=False,
            applicability_mode=ApplicabilityMode(source.applicability_mode),
            mapped_practice_keys=json.loads(source.mapped_practice_keys_json or "[]"),
            primary_interview_guidance=source.primary_interview_guidance,
            follow_up_guidance=source.follow_up_guidance,
            evidence_expectations=source.evidence_expectations,
            recommendation_when_unmet=source.recommendation_when_unmet,
            display_order=source.display_order + 1,
            conditions=[
                StandardConditionIn(
                    field=c.field,
                    operator=ConditionOperator(c.operator),
                    value=c.value,
                    logical_group=ConditionLogicalGroup(c.logical_group),
                )
                for c in source.conditions
            ],
        )
        return self.create_standard(payload, actor=actor)

    def delete_standard(self, standard_id: str, *, actor: str) -> None:
        row = self._require_standard(standard_id)
        refs = self.db.scalar(
            select(func.count())
            .select_from(AssessmentStandardSnapshot)
            .where(AssessmentStandardSnapshot.source_standard_id == standard_id)
        )
        if refs:
            raise AppError(
                code="standard_referenced",
                message="Cannot delete a standard that has been snapshotted for an assessment",
                status_code=409,
            )
        key = row.stable_key
        self.db.delete(row)
        self.audit.record(
            assessment_id=None,
            event_type="enterprise_standard.deleted",
            message=f"Deleted standard {key}",
            actor_type="admin",
            actor_subject=actor,
            details={"stable_key": key},
        )
        self.db.flush()

    def export_bundle(self) -> dict[str, Any]:
        return {
            "standards": [
                {
                    "stable_key": s.stable_key,
                    "title": s.title,
                    "category": s.category,
                    "description": s.description,
                    "requirement_level": s.requirement_level,
                    "active": s.active,
                    "applicability_mode": s.applicability_mode,
                    "mapped_practice_keys": json.loads(s.mapped_practice_keys_json or "[]"),
                    "primary_interview_guidance": s.primary_interview_guidance,
                    "follow_up_guidance": s.follow_up_guidance,
                    "evidence_expectations": s.evidence_expectations,
                    "recommendation_when_unmet": s.recommendation_when_unmet,
                    "display_order": s.display_order,
                    "conditions": [
                        {
                            "field": c.field,
                            "operator": c.operator,
                            "value": c.value,
                            "logical_group": c.logical_group,
                        }
                        for c in s.conditions
                    ],
                }
                for s in self.db.scalars(
                    select(EnterpriseStandard)
                    .options(selectinload(EnterpriseStandard.conditions))
                    .order_by(EnterpriseStandard.display_order)
                ).all()
            ]
        }

    def import_bundle(
        self, standards: list[EnterpriseStandardIn], *, actor: str, replace: bool = False
    ) -> list[EnterpriseStandardOut]:
        for item in standards:
            self._validate_payload(item)
        if replace:
            for existing in self.db.scalars(select(EnterpriseStandard)).all():
                refs = self.db.scalar(
                    select(func.count())
                    .select_from(AssessmentStandardSnapshot)
                    .where(AssessmentStandardSnapshot.source_standard_id == existing.id)
                )
                if not refs:
                    self.db.delete(existing)
            self.db.flush()
        outs: list[EnterpriseStandardOut] = []
        for item in standards:
            existing = self.db.scalar(
                select(EnterpriseStandard)
                .options(selectinload(EnterpriseStandard.conditions))
                .where(EnterpriseStandard.stable_key == item.stable_key)
            )
            if existing:
                outs.append(
                    self.update_standard(
                        existing.id,
                        EnterpriseStandardUpdate(
                            title=item.title,
                            category=item.category,
                            description=item.description,
                            requirement_level=item.requirement_level,
                            active=item.active,
                            applicability_mode=item.applicability_mode,
                            mapped_practice_keys=item.mapped_practice_keys,
                            primary_interview_guidance=item.primary_interview_guidance,
                            follow_up_guidance=item.follow_up_guidance,
                            evidence_expectations=item.evidence_expectations,
                            recommendation_when_unmet=item.recommendation_when_unmet,
                            display_order=item.display_order,
                            conditions=item.conditions,
                        ),
                        actor=actor,
                    )
                )
            else:
                outs.append(self.create_standard(item, actor=actor))
        return outs

    # ── technology context & applicability ────────────────────────────────────

    def upsert_technology_context(
        self, assessment_id: str, body: TechnologyContextIn, *, confirm: bool = False
    ) -> TechnologyContextOut:
        assessment = self._require_assessment(assessment_id)
        if AssessmentStatus(assessment.status) not in {
            AssessmentStatus.SETUP,
            AssessmentStatus.COLLECTING_EVIDENCE,
            AssessmentStatus.EVIDENCE_READY,
        }:
            raise AppError(
                code="invalid_state",
                message="Technology context can only be edited before the interview begins",
                status_code=409,
            )
        row = self.db.scalar(
            select(AssessmentTechnologyContext).where(
                AssessmentTechnologyContext.assessment_id == assessment_id
            )
        )
        if row is None:
            row = AssessmentTechnologyContext(assessment_id=assessment_id)
            self.db.add(row)
        row.primary_technology = body.primary_technology.strip()
        row.application_type = body.application_type.strip()
        row.current_platform = body.current_platform.strip()
        row.target_platform = body.target_platform.strip()
        row.hosting_location = body.hosting_location.strip()
        row.customer_exposure = body.customer_exposure.strip()
        row.lifecycle_stage = body.lifecycle_stage.strip()
        row.application_has_secrets = body.application_has_secrets
        row.uses_cicd = body.uses_cicd
        row.context_tags_json = json.dumps([t.strip() for t in body.context_tags if t.strip()])
        row.notes = body.notes.strip()
        if confirm:
            row.confirmed_at = datetime.now(UTC)
        self.db.flush()
        applicable = self.evaluate_applicable(assessment_id)
        return self._context_out(row, applicable)

    def get_technology_context(self, assessment_id: str) -> TechnologyContextOut | None:
        self._require_assessment(assessment_id)
        row = self.db.scalar(
            select(AssessmentTechnologyContext).where(
                AssessmentTechnologyContext.assessment_id == assessment_id
            )
        )
        if row is None:
            return None
        return self._context_out(row, self.evaluate_applicable(assessment_id))

    def evaluate_applicable(self, assessment_id: str) -> list[EnterpriseStandard]:
        context = self.db.scalar(
            select(AssessmentTechnologyContext).where(
                AssessmentTechnologyContext.assessment_id == assessment_id
            )
        )
        standards = self.db.scalars(
            select(EnterpriseStandard)
            .options(selectinload(EnterpriseStandard.conditions))
            .where(EnterpriseStandard.active.is_(True))
            .order_by(EnterpriseStandard.display_order)
        ).all()
        return [s for s in standards if self.is_applicable(s, context)]

    def is_applicable(
        self, standard: EnterpriseStandard, context: AssessmentTechnologyContext | None
    ) -> bool:
        if standard.applicability_mode == ApplicabilityMode.ALWAYS.value:
            return True
        if context is None:
            return False
        conditions = list(standard.conditions)
        if not conditions:
            return False
        all_group = [c for c in conditions if c.logical_group == ConditionLogicalGroup.ALL.value]
        any_group = [c for c in conditions if c.logical_group == ConditionLogicalGroup.ANY.value]
        all_ok = all(self._eval_condition(c, context) for c in all_group) if all_group else True
        any_ok = any(self._eval_condition(c, context) for c in any_group) if any_group else True
        # If only ALL rules: require all. If only ANY: require any. If both: ALL and (ANY).
        if all_group and any_group:
            return all_ok and any_ok
        if all_group:
            return all_ok
        return any_ok

    def _eval_condition(
        self, condition: EnterpriseStandardCondition, context: AssessmentTechnologyContext
    ) -> bool:
        field = condition.field
        if field not in APPLICABILITY_FIELDS:
            return False
        op = ConditionOperator(condition.operator)
        expected = (condition.value or "").strip()
        if field == "custom_context_tag":
            tags = [t.lower() for t in json.loads(context.context_tags_json or "[]")]
            needle = expected.lower()
            if op == ConditionOperator.CONTAINS or op == ConditionOperator.EQUALS:
                return needle in tags
            if op == ConditionOperator.IN:
                options = [p.strip().lower() for p in expected.split(",") if p.strip()]
                return any(t in options for t in tags)
            if op == ConditionOperator.NOT_EQUALS:
                return needle not in tags
            return False
        if field in {"application_has_secrets", "uses_cicd"}:
            actual = bool(getattr(context, field))
            if op == ConditionOperator.IS_TRUE:
                return actual is True
            if op == ConditionOperator.IS_FALSE:
                return actual is False
            if op == ConditionOperator.EQUALS:
                return actual == (expected.lower() in {"1", "true", "yes"})
            return False
        actual_s = str(getattr(context, field, "") or "").strip().lower()
        expected_l = expected.lower()
        if op == ConditionOperator.EQUALS:
            return actual_s == expected_l
        if op == ConditionOperator.NOT_EQUALS:
            return actual_s != expected_l
        if op == ConditionOperator.CONTAINS:
            return expected_l in actual_s
        if op == ConditionOperator.IN:
            options = [p.strip().lower() for p in expected.split(",") if p.strip()]
            return actual_s in options
        return False

    # ── snapshots & findings ──────────────────────────────────────────────────

    def snapshot_applicable(self, assessment_id: str) -> list[AssessmentStandardSnapshot]:
        """Immutable snapshots at interview start. Idempotent if already snapshotted."""
        existing = self.db.scalars(
            select(AssessmentStandardSnapshot).where(
                AssessmentStandardSnapshot.assessment_id == assessment_id
            )
        ).all()
        if existing:
            return list(existing)
        applicable = self.evaluate_applicable(assessment_id)
        now = datetime.now(UTC)
        created: list[AssessmentStandardSnapshot] = []
        for standard in applicable:
            definition = self._serialize_definition(standard)
            snap = AssessmentStandardSnapshot(
                assessment_id=assessment_id,
                source_standard_id=standard.id,
                stable_key=standard.stable_key,
                definition_json=json.dumps(definition),
                source_updated_at=standard.updated_at,
                snapshot_at=now,
            )
            self.db.add(snap)
            self.db.flush()
            finding = AssessmentStandardFinding(
                assessment_id=assessment_id,
                snapshot_id=snap.id,
                status=StandardFindingStatus.INSUFFICIENT_EVIDENCE.value,
                recommendation=standard.recommendation_when_unmet,
            )
            self.db.add(finding)
            created.append(snap)
        self.db.flush()
        return created

    def list_snapshots(self, assessment_id: str) -> list[StandardSnapshotOut]:
        self._require_assessment(assessment_id)
        rows = self.db.scalars(
            select(AssessmentStandardSnapshot).where(
                AssessmentStandardSnapshot.assessment_id == assessment_id
            )
        ).all()
        return [
            StandardSnapshotOut(
                id=r.id,
                assessment_id=r.assessment_id,
                source_standard_id=r.source_standard_id,
                stable_key=r.stable_key,
                definition=json.loads(r.definition_json),
                source_updated_at=r.source_updated_at,
                snapshot_at=r.snapshot_at,
            )
            for r in rows
        ]

    def list_findings(self, assessment_id: str) -> list[StandardFindingOut]:
        self._require_assessment(assessment_id)
        rows = self.db.scalars(
            select(AssessmentStandardFinding)
            .options(selectinload(AssessmentStandardFinding.snapshot))
            .where(AssessmentStandardFinding.assessment_id == assessment_id)
        ).all()
        return [self._finding_out(r) for r in rows]

    def update_finding(
        self, assessment_id: str, finding_id: str, body: StandardFindingUpdateIn, *, actor: str
    ) -> StandardFindingOut:
        row = self.db.scalar(
            select(AssessmentStandardFinding)
            .options(selectinload(AssessmentStandardFinding.snapshot))
            .where(
                AssessmentStandardFinding.id == finding_id,
                AssessmentStandardFinding.assessment_id == assessment_id,
            )
        )
        if row is None:
            raise AppError(
                code="finding_not_found", message="Standard finding not found", status_code=404
            )
        if body.status is not None:
            row.status = body.status.value
            row.admin_edited_status = True
        if body.observation is not None:
            row.observation = sanitize_remote_text(body.observation, max_len=4000)
        if body.recommendation is not None:
            row.recommendation = sanitize_remote_text(body.recommendation, max_len=4000)
        if body.admin_note is not None:
            row.admin_note = sanitize_remote_text(body.admin_note, max_len=2000)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="enterprise_finding.updated",
            message="Admin updated enterprise standard finding",
            actor_type="admin",
            actor_subject=actor,
            details={"finding_id": finding_id, "status": row.status},
        )
        self.db.flush()
        return self._finding_out(row)

    def apply_standard_updates_from_analysis(
        self,
        assessment_id: str,
        updates: list[Any],
        *,
        turn_id: str | None = None,
    ) -> None:
        """Apply model-proposed standard updates; reject unknown keys."""
        snaps = {
            s.stable_key: s
            for s in self.db.scalars(
                select(AssessmentStandardSnapshot).where(
                    AssessmentStandardSnapshot.assessment_id == assessment_id
                )
            ).all()
        }
        findings = {
            f.snapshot_id: f
            for f in self.db.scalars(
                select(AssessmentStandardFinding).where(
                    AssessmentStandardFinding.assessment_id == assessment_id
                )
            ).all()
        }
        for update in updates:
            key = getattr(update, "standard_key", None) or (
                update.get("standard_key") if isinstance(update, dict) else None
            )
            if not key or key not in snaps:
                raise AppError(
                    code="unknown_standard_key",
                    message="Model referenced an unknown or non-applicable enterprise standard",
                    status_code=400,
                    details={"standard_key": key},
                )
            snap = snaps[key]
            finding = findings.get(snap.id)
            if finding is None:
                continue
            if finding.admin_edited_status:
                continue  # preserve admin overrides during interview
            status = getattr(update, "status", None) or update.get("status")
            if hasattr(status, "value"):
                status = status.value
            if status not in {s.value for s in StandardFindingStatus}:
                status = StandardFindingStatus.INSUFFICIENT_EVIDENCE.value
            if getattr(update, "applicability_confirmation", True) is False:
                status = StandardFindingStatus.NOT_APPLICABLE.value
            finding.status = status
            summary = sanitize_remote_text(
                getattr(update, "evidence_summary", None)
                or (update.get("evidence_summary") if isinstance(update, dict) else "")
                or "",
                max_len=4000,
            )
            finding.human_evidence_summary = summary
            finding.confidence = float(
                getattr(update, "confidence", None)
                or (update.get("confidence") if isinstance(update, dict) else 0.5)
                or 0.5
            )
            missing = (
                getattr(update, "missing_evidence", None)
                or (update.get("missing_evidence") if isinstance(update, dict) else [])
                or []
            )
            finding.observation = summary or "; ".join(str(m) for m in missing)
            rec = sanitize_remote_text(
                getattr(update, "recommendation_candidate", None)
                or (update.get("recommendation_candidate") if isinstance(update, dict) else "")
                or finding.recommendation,
                max_len=4000,
            )
            if rec:
                finding.recommendation = rec
            if turn_id:
                turns = json.loads(finding.source_interview_turn_ids_json or "[]")
                if turn_id not in turns:
                    turns.append(turn_id)
                    finding.source_interview_turn_ids_json = json.dumps(turns)
        self.db.flush()

    def interview_context_payload(self, assessment_id: str) -> dict[str, Any]:
        snaps = self.list_snapshots(assessment_id)
        findings = self.list_findings(assessment_id)
        return {
            "applicable_standards": [
                {
                    "stable_key": s.stable_key,
                    "title": s.definition.get("title"),
                    "category": s.definition.get("category"),
                    "requirement_level": s.definition.get("requirement_level"),
                    "mapped_practice_keys": s.definition.get("mapped_practice_keys") or [],
                    "primary_interview_guidance": s.definition.get("primary_interview_guidance")
                    or "",
                    "follow_up_guidance": s.definition.get("follow_up_guidance") or "",
                    "evidence_expectations": s.definition.get("evidence_expectations") or "",
                    "recommendation_when_unmet": s.definition.get("recommendation_when_unmet")
                    or "",
                }
                for s in snaps
            ],
            "standard_findings": [
                {
                    "stable_key": f.stable_key,
                    "status": f.status.value,
                    "confidence": f.confidence,
                    "missing_evidence": f.observation
                    if f.status == StandardFindingStatus.INSUFFICIENT_EVIDENCE
                    else "",
                }
                for f in findings
            ],
            "known_standard_keys": [s.stable_key for s in snaps],
        }

    def published_section(self, assessment_id: str) -> dict[str, Any]:
        findings = self.list_findings(assessment_id)
        counts = {
            "applicable_count": len(findings),
            "aligned_count": sum(1 for f in findings if f.status == StandardFindingStatus.ALIGNED),
            "partially_aligned_count": sum(
                1 for f in findings if f.status == StandardFindingStatus.PARTIALLY_ALIGNED
            ),
            "finding_count": sum(1 for f in findings if f.status == StandardFindingStatus.FINDING),
            "insufficient_evidence_count": sum(
                1 for f in findings if f.status == StandardFindingStatus.INSUFFICIENT_EVIDENCE
            ),
            "not_applicable_count": sum(
                1 for f in findings if f.status == StandardFindingStatus.NOT_APPLICABLE
            ),
        }
        by_category: dict[str, list[dict[str, Any]]] = {}
        cards: list[dict[str, Any]] = []
        for f in findings:
            if f.status in {StandardFindingStatus.NOT_APPLICABLE}:
                continue
            item = {
                "standard": f.title,
                "stable_key": f.stable_key,
                "category": f.category,
                "requirement_level": f.requirement_level.value,
                "status": f.status.value,
                "observation": f.observation,
                "supporting_evidence": f.human_evidence_summary or f.tool_evidence_summary,
                "recommendation": f.recommendation,
                "related_safe_practices": f.mapped_practice_keys,
                "suggested_time_horizon": f.time_horizon,
            }
            by_category.setdefault(f.category, []).append(item)
            if f.status in {
                StandardFindingStatus.FINDING,
                StandardFindingStatus.PARTIALLY_ALIGNED,
                StandardFindingStatus.INSUFFICIENT_EVIDENCE,
            }:
                cards.append(item)
        return {**counts, "findings_by_category": by_category, "recommendation_cards": cards}

    def seed_library(self) -> list[EnterpriseStandardOut]:
        """Idempotent demo standards."""
        seeds = _demo_standards()
        return self.import_bundle(seeds, actor="seed", replace=False)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _validate_payload(self, body: EnterpriseStandardIn) -> None:
        if not SAFE_KEY_RE.match(body.stable_key):
            raise AppError(code="invalid_stable_key", message="Invalid stable_key", status_code=400)
        self._validate_practice_keys(body.mapped_practice_keys)
        if body.applicability_mode == ApplicabilityMode.CONDITIONS and not body.conditions:
            raise AppError(
                code="conditions_required",
                message="Conditional standards require at least one applicability rule",
                status_code=400,
            )
        for condition in body.conditions:
            if condition.field not in APPLICABILITY_FIELDS:
                raise AppError(
                    code="invalid_condition_field",
                    message=f"Unsupported field {condition.field}",
                    status_code=400,
                )
            # Reject regex/SQL-looking values as a soft guard
            if any(tok in condition.value for tok in (";", "--", "/*", "*/", "(?", "\\")):
                raise AppError(
                    code="invalid_condition_value",
                    message="Condition values cannot contain executable patterns",
                    status_code=400,
                )

    def _validate_practice_keys(self, keys: list[str]) -> None:
        known = set(self.model.practice_keys())
        unknown = [k for k in keys if k not in known]
        if unknown:
            raise AppError(
                code="unknown_practice_keys",
                message="Unknown SAFe practice keys",
                status_code=400,
                details={"unknown": unknown},
            )

    def _replace_conditions(
        self, row: EnterpriseStandard, conditions: list[StandardConditionIn]
    ) -> None:
        row.conditions.clear()
        self.db.flush()
        for condition in conditions:
            row.conditions.append(
                EnterpriseStandardCondition(
                    field=condition.field,
                    operator=condition.operator.value,
                    value=condition.value,
                    logical_group=condition.logical_group.value,
                )
            )
        self.db.flush()

    def _require_standard(self, standard_id: str) -> EnterpriseStandard:
        row = self.db.scalar(
            select(EnterpriseStandard)
            .options(selectinload(EnterpriseStandard.conditions))
            .where(EnterpriseStandard.id == standard_id)
        )
        if row is None:
            raise AppError(
                code="standard_not_found", message="Enterprise standard not found", status_code=404
            )
        return row

    def _require_assessment(self, assessment_id: str) -> Assessment:
        row = self.db.get(Assessment, assessment_id)
        if row is None:
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return row

    def _serialize_definition(self, standard: EnterpriseStandard) -> dict[str, Any]:
        return {
            "stable_key": standard.stable_key,
            "title": standard.title,
            "category": standard.category,
            "description": standard.description,
            "requirement_level": standard.requirement_level,
            "applicability_mode": standard.applicability_mode,
            "mapped_practice_keys": json.loads(standard.mapped_practice_keys_json or "[]"),
            "primary_interview_guidance": standard.primary_interview_guidance,
            "follow_up_guidance": standard.follow_up_guidance,
            "evidence_expectations": standard.evidence_expectations,
            "recommendation_when_unmet": standard.recommendation_when_unmet,
            "display_order": standard.display_order,
            "conditions": [
                {
                    "field": c.field,
                    "operator": c.operator,
                    "value": c.value,
                    "logical_group": c.logical_group,
                }
                for c in standard.conditions
            ],
        }

    def _to_out(self, row: EnterpriseStandard) -> EnterpriseStandardOut:
        refs = self.db.scalar(
            select(func.count())
            .select_from(AssessmentStandardSnapshot)
            .where(AssessmentStandardSnapshot.source_standard_id == row.id)
        )
        return EnterpriseStandardOut(
            id=row.id,
            stable_key=row.stable_key,
            title=row.title,
            category=row.category,
            description=row.description,
            requirement_level=RequirementLevel(row.requirement_level),
            active=row.active,
            applicability_mode=ApplicabilityMode(row.applicability_mode),
            mapped_practice_keys=json.loads(row.mapped_practice_keys_json or "[]"),
            primary_interview_guidance=row.primary_interview_guidance,
            follow_up_guidance=row.follow_up_guidance,
            evidence_expectations=row.evidence_expectations,
            recommendation_when_unmet=row.recommendation_when_unmet,
            display_order=row.display_order,
            conditions=[
                StandardConditionOut(
                    id=c.id,
                    field=c.field,
                    operator=ConditionOperator(c.operator),
                    value=c.value,
                    logical_group=ConditionLogicalGroup(c.logical_group),
                )
                for c in row.conditions
            ],
            referenced=bool(refs),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _context_out(
        self, row: AssessmentTechnologyContext, applicable: list[EnterpriseStandard]
    ) -> TechnologyContextOut:
        return TechnologyContextOut(
            id=row.id,
            assessment_id=row.assessment_id,
            primary_technology=row.primary_technology,
            application_type=row.application_type,
            current_platform=row.current_platform,
            target_platform=row.target_platform,
            hosting_location=row.hosting_location,
            customer_exposure=row.customer_exposure,
            lifecycle_stage=row.lifecycle_stage,
            application_has_secrets=row.application_has_secrets,
            uses_cicd=row.uses_cicd,
            context_tags=json.loads(row.context_tags_json or "[]"),
            notes=row.notes,
            confirmed_at=row.confirmed_at,
            applicable_standard_count=len(applicable),
            applicable_standard_keys=[s.stable_key for s in applicable],
        )

    def _finding_out(self, row: AssessmentStandardFinding) -> StandardFindingOut:
        definition = json.loads(row.snapshot.definition_json)
        level = RequirementLevel(definition.get("requirement_level", "preferred"))
        horizon = "next_sprint" if level == RequirementLevel.REQUIRED else "ninety_days"
        if level == RequirementLevel.RECOMMENDED:
            horizon = "longer_term"
        return StandardFindingOut(
            id=row.id,
            assessment_id=row.assessment_id,
            snapshot_id=row.snapshot_id,
            stable_key=row.snapshot.stable_key,
            title=definition.get("title") or row.snapshot.stable_key,
            category=definition.get("category") or "general",
            requirement_level=level,
            mapped_practice_keys=definition.get("mapped_practice_keys") or [],
            status=StandardFindingStatus(row.status),
            human_evidence_summary=row.human_evidence_summary,
            tool_evidence_summary=row.tool_evidence_summary,
            source_interview_turn_ids=json.loads(row.source_interview_turn_ids_json or "[]"),
            source_evidence_metric_ids=json.loads(row.source_evidence_metric_ids_json or "[]"),
            confidence=row.confidence,
            observation=row.observation,
            recommendation=row.recommendation,
            admin_edited_status=row.admin_edited_status,
            admin_note=row.admin_note,
            time_horizon=horizon,
        )


def _demo_standards() -> list[EnterpriseStandardIn]:
    return [
        EnterpriseStandardIn(
            stable_key="approved_secret_management",
            title="Approved secret management",
            category="Security",
            description="Secrets must be retrieved from Secret Server rather than hardcoded in source or pipelines.",
            requirement_level=RequirementLevel.REQUIRED,
            active=True,
            applicability_mode=ApplicabilityMode.CONDITIONS,
            mapped_practice_keys=["develop", "build", "deploy"],
            primary_interview_guidance=(
                "Ask how credentials and API tokens are provided to builds and deployments, "
                "and whether Secret Server (or an approved vault) is required."
            ),
            follow_up_guidance="Clarify whether any service accounts or connection strings remain in repo config.",
            evidence_expectations="Pipeline variable groups, Secret Server integration mentions, absence of hardcoded tokens.",
            recommendation_when_unmet=(
                "Require Secret Server (or approved vault) retrieval for runtime and pipeline secrets; "
                "remove hardcoded credentials from repositories and variable files."
            ),
            display_order=10,
            conditions=[
                StandardConditionIn(
                    field="application_has_secrets",
                    operator=ConditionOperator.IS_TRUE,
                    value="true",
                    logical_group=ConditionLogicalGroup.ALL,
                )
            ],
        ),
        EnterpriseStandardIn(
            stable_key="preferred_java_runtime_openshift",
            title="Preferred runtime for Java applications",
            category="Platform",
            description="OpenShift is preferred over WebSphere for applicable Java applications.",
            requirement_level=RequirementLevel.PREFERRED,
            active=True,
            applicability_mode=ApplicabilityMode.CONDITIONS,
            mapped_practice_keys=["architect", "stage", "deploy", "stabilize"],
            primary_interview_guidance=(
                "If the application is Java, ask about current and target runtime platforms "
                "and any plan to move off WebSphere toward OpenShift."
            ),
            follow_up_guidance="Capture constraints that keep the app on WebSphere if applicable.",
            evidence_expectations="Target platform statements, deployment manifests, platform roadmap notes.",
            recommendation_when_unmet=(
                "Plan migration of applicable Java workloads from WebSphere to the approved OpenShift platform, "
                "with staged cutover and rollback criteria."
            ),
            display_order=20,
            conditions=[
                StandardConditionIn(
                    field="primary_technology",
                    operator=ConditionOperator.EQUALS,
                    value="Java",
                    logical_group=ConditionLogicalGroup.ALL,
                )
            ],
        ),
        EnterpriseStandardIn(
            stable_key="pull_request_quality_gates",
            title="Pull-request quality gates",
            category="Delivery",
            description="Approved quality gates should run during pull-request validation before merge.",
            requirement_level=RequirementLevel.REQUIRED,
            active=True,
            applicability_mode=ApplicabilityMode.CONDITIONS,
            mapped_practice_keys=["build", "test_end_to_end"],
            primary_interview_guidance=(
                "Ask which checks must pass on a pull request before merge, and whether they are required or optional."
            ),
            follow_up_guidance="Probe for secret scanning, unit tests, and policy gates in PR validation.",
            evidence_expectations="ADO PR pipeline definitions, required status checks, recent PR run results.",
            recommendation_when_unmet=(
                "Make approved quality gates required on pull-request validation, including tests and policy checks, "
                "before merge to the protected branch."
            ),
            display_order=30,
            conditions=[
                StandardConditionIn(
                    field="uses_cicd",
                    operator=ConditionOperator.IS_TRUE,
                    value="true",
                    logical_group=ConditionLogicalGroup.ALL,
                )
            ],
        ),
        EnterpriseStandardIn(
            stable_key="approved_deployment_automation",
            title="Approved deployment automation",
            category="Delivery",
            description="Production changes should use approved deployment pipelines rather than ad-hoc scripts.",
            requirement_level=RequirementLevel.PREFERRED,
            active=True,
            applicability_mode=ApplicabilityMode.ALWAYS,
            mapped_practice_keys=["stage", "deploy"],
            primary_interview_guidance=(
                "Ask how production changes are promoted and whether an approved CD pipeline is mandatory."
            ),
            follow_up_guidance="Identify any manual hotfixes that bypass the approved pipeline.",
            evidence_expectations="ADO release/CD pipelines, environment approvals, deployment frequency.",
            recommendation_when_unmet=(
                "Route production changes through the approved deployment pipeline with environment gates; "
                "retire ad-hoc production scripts for routine releases."
            ),
            display_order=40,
            conditions=[],
        ),
        EnterpriseStandardIn(
            stable_key="approved_production_observability",
            title="Approved production observability",
            category="Operations",
            description="Applications should use approved monitoring and logging capabilities in production.",
            requirement_level=RequirementLevel.REQUIRED,
            active=True,
            applicability_mode=ApplicabilityMode.ALWAYS,
            mapped_practice_keys=["monitor", "respond", "stabilize"],
            primary_interview_guidance=(
                "Ask what monitoring and logging are required after production deploy, and how incidents are detected."
            ),
            follow_up_guidance="Confirm dashboards, alerting routes, and log retention align with approved tooling.",
            evidence_expectations="Monitoring dashboards, alert policies, on-call runbooks, log platform references.",
            recommendation_when_unmet=(
                "Onboard the service to approved monitoring and logging platforms with actionable alerts "
                "for customer-impacting paths before the next production release."
            ),
            display_order=50,
            conditions=[],
        ),
    ]
