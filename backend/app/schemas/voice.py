from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoicePrivacyOut(StrictSchema):
    retain_source_audio: bool
    retain_corrected_transcript: bool
    storage_mode: Literal["ephemeral_tmp", "retained_upload", "browser_only"]
    privacy_notice: str


class RealtimeSessionIn(StrictSchema):
    assessment_id: str | None = None
    topic_label: str | None = Field(default=None, max_length=120)


class RealtimeSessionOut(StrictSchema):
    """Ephemeral Realtime credentials for browser WebRTC. Never includes OPENAI_API_KEY."""

    client_secret: str
    expires_at: datetime
    provider: Literal["mock", "live"]
    realtime_calls_url: str = "https://api.openai.com/v1/realtime/calls"
    transcription_model: str
    live_transcription_model: str
    final_transcription_model: str
    live_delay: str
    languages: list[str] = Field(default_factory=lambda: ["en"])
    language: str | None = None
    stop_mode: Literal["manual", "vad"]
    silence_timeout_ms: int
    max_recording_seconds: int
    voice_enabled: bool
    final_refinement_enabled: bool
    session_config: dict
    transcription_context: dict
    privacy: VoicePrivacyOut


class VoiceSettingsOut(StrictSchema):
    voice_enabled: bool
    transcription_model: str
    live_transcription_model: str
    final_transcription_model: str
    available_live_transcription_models: list[str]
    available_final_transcription_models: list[str]
    available_transcription_models: list[str]
    live_delay: Literal["minimal", "low", "medium", "high", "xhigh"]
    expected_languages: list[str]
    company_vocabulary: list[str]
    final_refinement_enabled: bool
    voice_language: str
    available_languages: list[str]
    voice_stop_mode: Literal["manual", "vad"]
    silence_timeout_ms: int
    max_recording_seconds: int
    retain_source_audio: bool
    retain_corrected_transcript: bool
    remote_voice_enabled: bool


class VoiceSettingsUpdate(StrictSchema):
    voice_enabled: bool | None = None
    transcription_model: str | None = None
    live_transcription_model: str | None = None
    final_transcription_model: str | None = None
    live_delay: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
    expected_languages: list[str] | None = None
    company_vocabulary: list[str] | None = None
    final_refinement_enabled: bool | None = None
    voice_language: str | None = None
    voice_stop_mode: Literal["manual", "vad"] | None = None
    silence_timeout_ms: int | None = Field(default=None, ge=200, le=10000)
    max_recording_seconds: int | None = Field(default=None, ge=30, le=3600)
    retain_source_audio: bool | None = None
    retain_corrected_transcript: bool | None = None
    remote_voice_enabled: bool | None = None


class TempAudioRegisterIn(StrictSchema):
    assessment_id: str | None = None
    filename: str = Field(default="capture.webm", max_length=120)


class TempAudioOut(StrictSchema):
    id: str
    path_label: str
    retained: bool
    expires_at: datetime
    cleaned_up: bool


class TempAudioCleanupOut(StrictSchema):
    id: str
    cleaned_up: bool
    removed: bool


class VoiceClientEventIn(StrictSchema):
    """Browser-side voice diagnostics (no secrets; logged server-side for Railway)."""

    stage: str = Field(max_length=64)
    name: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=400)
    secure_context: bool | None = None
    in_iframe: bool | None = None
    user_agent: str | None = Field(default=None, max_length=200)


class RefineTranscriptOut(StrictSchema):
    transcript: str
    model: str
    used_live_fallback: bool = False
    audio_id: str | None = None
    retained: bool = False
    refined: bool = True
    warning: str | None = None
    duration_ms: int | None = None


class VoiceMetricsIn(StrictSchema):
    """Safe operational metrics — never includes transcripts, audio, or secrets."""

    connection_duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    time_to_first_delta_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    recording_duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    refine_duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    transcript_item_count: int | None = Field(default=None, ge=0, le=10_000)
    empty_transcript: bool | None = None
    refinement_failed: bool | None = None
    webrtc_reconnect: bool | None = None
    mic_permission_failure: bool | None = None
    device_label: str | None = Field(default=None, max_length=200)
    live_model: str | None = Field(default=None, max_length=120)
    final_model: str | None = Field(default=None, max_length=120)


class VoiceDiagnosticsOut(StrictSchema):
    session_count: int
    avg_connection_duration_ms: float | None
    avg_time_to_first_delta_ms: float | None
    avg_recording_duration_ms: float | None
    avg_refine_duration_ms: float | None
    transcript_item_count: int
    empty_transcript_count: int
    refinement_failure_count: int
    webrtc_reconnect_count: int
    mic_permission_failure_count: int
    refinement_failure_rate: float | None
    live_model: str
    final_model: str
    last_device_label: str | None
