from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import InterviewTurnSource, InterviewTurnType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class InterviewTurn(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("assessment_id", "idempotency_key", name="uq_interview_turn_idempotency"),
        UniqueConstraint("assessment_id", "sequence", name="uq_interview_turn_sequence"),
    )

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=InterviewTurnType.BROAD.value
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default=InterviewTurnSource.ROOM_TYPED.value
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    practice_keys_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    structured_analysis_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    # Untrusted external/user content marker for downstream AI handling.
    content_trust: Mapped[str] = mapped_column(String(32), nullable=False, default="untrusted")

    assessment: Mapped[Assessment] = relationship(back_populates="interview_turns")
