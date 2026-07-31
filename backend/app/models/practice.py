from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CoverageState
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class PracticeCoverage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "practice_coverages"
    __table_args__ = (
        UniqueConstraint("assessment_id", "practice_key", name="uq_practice_coverage_assessment_practice"),
    )

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    practice_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    domain_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    coverage_state: Mapped[str] = mapped_column(String(32), nullable=False, default=CoverageState.NOT_DISCUSSED.value)
    evidence_summaries_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_turn_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    open_gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contradictions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    admin_final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    admin_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="practice_coverages")
