from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import (
    ApplicabilityMode,
    ConditionLogicalGroup,
    ConditionOperator,
    RequirementLevel,
    StandardFindingStatus,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class EnterpriseStandard(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "enterprise_standards"
    __table_args__ = (UniqueConstraint("stable_key", name="uq_enterprise_standard_stable_key"),)

    stable_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requirement_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RequirementLevel.PREFERRED.value, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    applicability_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ApplicabilityMode.ALWAYS.value
    )
    mapped_practice_keys_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    primary_interview_guidance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    follow_up_guidance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_expectations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendation_when_unmet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    conditions: Mapped[list[EnterpriseStandardCondition]] = relationship(
        back_populates="standard",
        cascade="all, delete-orphan",
        order_by="EnterpriseStandardCondition.id",
    )
    snapshots: Mapped[list[AssessmentStandardSnapshot]] = relationship(
        back_populates="source_standard"
    )


class EnterpriseStandardCondition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "enterprise_standard_conditions"

    standard_id: Mapped[str] = mapped_column(
        ForeignKey("enterprise_standards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConditionOperator.EQUALS.value
    )
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    logical_group: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ConditionLogicalGroup.ALL.value
    )

    standard: Mapped[EnterpriseStandard] = relationship(back_populates="conditions")


class AssessmentTechnologyContext(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessment_technology_contexts"
    __table_args__ = (UniqueConstraint("assessment_id", name="uq_assessment_technology_context"),)

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    primary_technology: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    application_type: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    current_platform: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    target_platform: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    hosting_location: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    customer_exposure: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    lifecycle_stage: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    application_has_secrets: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    uses_cicd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    context_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="technology_context")


class AssessmentStandardSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessment_standard_snapshots"
    __table_args__ = (
        UniqueConstraint("assessment_id", "stable_key", name="uq_assessment_standard_snapshot_key"),
    )

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_standard_id: Mapped[str | None] = mapped_column(
        ForeignKey("enterprise_standards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stable_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    assessment: Mapped[Assessment] = relationship(back_populates="standard_snapshots")
    source_standard: Mapped[EnterpriseStandard | None] = relationship(back_populates="snapshots")
    findings: Mapped[list[AssessmentStandardFinding]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class AssessmentStandardFinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessment_standard_findings"
    __table_args__ = (
        UniqueConstraint("assessment_id", "snapshot_id", name="uq_assessment_standard_finding"),
    )

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_standard_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=StandardFindingStatus.INSUFFICIENT_EVIDENCE.value,
        index=True,
    )
    human_evidence_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_evidence_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_interview_turn_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_evidence_metric_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    observation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    admin_edited_status: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    assessment: Mapped[Assessment] = relationship(back_populates="standard_findings")
    snapshot: Mapped[AssessmentStandardSnapshot] = relationship(back_populates="findings")
