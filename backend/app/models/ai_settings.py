from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AiRuntimeSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Singleton runtime AI settings editable by admins."""

    __tablename__ = "ai_runtime_settings"

    singleton_key: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, default="default"
    )
    assessment_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gpt-5.6-terra"
    )
    reasoning_effort: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    interview_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="mock")
    transcription_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gpt-live-transcribe"
    )
    live_transcription_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gpt-live-transcribe"
    )
    final_transcription_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="gpt-transcribe"
    )
    live_delay: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    expected_languages_json: Mapped[str] = mapped_column(Text, nullable=False, default='["en"]')
    company_vocabulary_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    final_refinement_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    voice_language: Mapped[str] = mapped_column(String(32), nullable=False, default="en")
    voice_stop_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    silence_timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    max_recording_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    retain_source_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retain_corrected_transcript: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remote_voice_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VoiceTempAudio(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks ephemeral or explicitly retained voice capture files."""

    __tablename__ = "voice_temp_audio"

    assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    retained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cleaned_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VoiceDiagnosticsCounters(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Aggregate safe operational metrics for voice (no transcripts/audio)."""

    __tablename__ = "voice_diagnostics_counters"

    singleton_key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, default="default")
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connection_duration_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_to_first_delta_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_to_first_delta_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recording_duration_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refine_duration_ms_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refine_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transcript_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_transcript_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refinement_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    webrtc_reconnect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mic_permission_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    live_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    final_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    last_device_label: Mapped[str | None] = mapped_column(String(200), nullable=True)


class InterviewSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_sessions"

    assessment_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    interview_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    current_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_asking: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_label: Mapped[str] = mapped_column(
        String(120), nullable=False, default="Delivery journey"
    )
    pending_clarification: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    overall_coverage_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    coverage_confirmation: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_config_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="assessment_model.yaml"
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-5.6-terra")
    reasoning_effort: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    provider_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mock")
    last_telemetry_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    answered_turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_analysis_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
