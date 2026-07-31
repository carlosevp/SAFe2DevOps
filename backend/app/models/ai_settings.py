from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AiRuntimeSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Singleton runtime AI settings editable by admins."""

    __tablename__ = "ai_runtime_settings"

    singleton_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, default="default")
    assessment_model: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-5.6-terra")
    reasoning_effort: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    interview_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="mock")
    transcription_model: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-realtime-whisper")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InterviewSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_sessions"

    assessment_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    interview_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    current_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_asking: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_label: Mapped[str] = mapped_column(String(120), nullable=False, default="Delivery journey")
    pending_clarification: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    overall_coverage_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    coverage_confirmation: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_config_version: Mapped[str] = mapped_column(String(80), nullable=False, default="assessment_model.yaml")
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-5.6-terra")
    reasoning_effort: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    provider_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mock")
    last_telemetry_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    answered_turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_analysis_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
