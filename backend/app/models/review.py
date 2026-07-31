from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class AssessmentReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessment_reviews"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_subject: Mapped[str] = mapped_column(String(200), nullable=False, default="admin")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ready_to_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scoring_telemetry_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    overall_maturity: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_summary: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_quality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    strengths_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    maturity_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    limitations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    assessment: Mapped[Assessment] = relationship(back_populates="reviews")


class ImprovementAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "improvement_actions"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    practice_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    domain_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    supporting_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    time_horizon: Mapped[str] = mapped_column(String(32), nullable=False, default="next_sprint")
    kpi: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    owner_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    assessment: Mapped[Assessment] = relationship(back_populates="improvement_actions")


class PublishedReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned immutable publication artifact."""

    __tablename__ = "published_reports"
    __table_args__ = (
        UniqueConstraint("assessment_id", "version", name="uq_published_report_version"),
    )

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    radar_json: Mapped[str] = mapped_column(Text, nullable=False)
    heatmap_json: Mapped[str] = mapped_column(Text, nullable=False)
    scores_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # admin final scores only (public)
    improvement_plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    published_by: Mapped[str] = mapped_column(String(200), nullable=False, default="admin")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    overall_maturity: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_summary: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_quality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    strengths_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    maturity_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    limitations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    evidence_influence_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="balanced"
    )
    prompt_config_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="assessment_model.yaml"
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="mock")
    ai_vs_final_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )  # admin-only comparison
    export_json_relpath: Mapped[str | None] = mapped_column(String(500), nullable=True)
    export_pdf_relpath: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chart_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    assessment: Mapped[Assessment] = relationship(back_populates="published_reports")
