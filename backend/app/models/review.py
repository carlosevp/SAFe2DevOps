from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class AssessmentReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessment_reviews"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_subject: Mapped[str] = mapped_column(String(200), nullable=False, default="admin")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ready_to_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="reviews")


class ImprovementAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "improvement_actions"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    practice_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    owner_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    assessment: Mapped[Assessment] = relationship(back_populates="improvement_actions")


class PublishedReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned immutable publication artifact."""

    __tablename__ = "published_reports"
    __table_args__ = (UniqueConstraint("assessment_id", "version", name="uq_published_report_version"),)

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    radar_json: Mapped[str] = mapped_column(Text, nullable=False)
    heatmap_json: Mapped[str] = mapped_column(Text, nullable=False)
    scores_json: Mapped[str] = mapped_column(Text, nullable=False)  # admin final scores only
    improvement_plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    published_by: Mapped[str] = mapped_column(String(200), nullable=False, default="admin")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    assessment: Mapped[Assessment] = relationship(back_populates="published_reports")
