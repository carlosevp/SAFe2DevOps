from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class EvidenceSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_snapshots"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    jira_project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ado_repository_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provenance_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Keep normalized references only; avoid bloating SQLite with raw payloads.
    raw_payload_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_representative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="evidence_snapshots")
    metrics: Mapped[list[EvidenceMetric]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")
    limitations: Mapped[list[EvidenceLimitation]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")
    exclusions: Mapped[list[EvidenceExclusion]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class EvidenceMetric(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_metrics"

    snapshot_id: Mapped[str] = mapped_column(ForeignKey("evidence_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    value_text: Mapped[str] = mapped_column(String(120), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)  # jira | azdo
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    freshness_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    practice_keys_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    snapshot: Mapped[EvidenceSnapshot] = relationship(back_populates="metrics")


class EvidenceLimitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_limitations"

    snapshot_id: Mapped[str] = mapped_column(ForeignKey("evidence_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(32), nullable=True)

    snapshot: Mapped[EvidenceSnapshot] = relationship(back_populates="limitations")


class EvidenceExclusion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_exclusions"

    snapshot_id: Mapped[str] = mapped_column(ForeignKey("evidence_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_by: Mapped[str] = mapped_column(String(120), nullable=False)
    scope_label: Mapped[str] = mapped_column(String(200), nullable=False)

    snapshot: Mapped[EvidenceSnapshot] = relationship(back_populates="exclusions")
