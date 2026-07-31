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


class RealtimeSessionOut(StrictSchema):
    """Ephemeral Realtime credentials for browser WebRTC. Never includes OPENAI_API_KEY."""

    client_secret: str
    expires_at: datetime
    provider: Literal["mock", "live"]
    realtime_calls_url: str = "https://api.openai.com/v1/realtime/calls"
    transcription_model: str
    language: str | None = None
    stop_mode: Literal["manual", "vad"]
    silence_timeout_ms: int
    max_recording_seconds: int
    voice_enabled: bool
    session_config: dict
    privacy: VoicePrivacyOut


class VoiceSettingsOut(StrictSchema):
    voice_enabled: bool
    transcription_model: str
    available_transcription_models: list[str]
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
