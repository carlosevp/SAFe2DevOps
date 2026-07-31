from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import redact_secrets
from app.models.ai_settings import AiRuntimeSettings, VoiceTempAudio
from app.schemas.voice import RealtimeSessionOut, TempAudioOut, VoicePrivacyOut, VoiceSettingsOut
from app.services.ai_settings import AiSettingsService
from app.services.audit import AuditService
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

AVAILABLE_TRANSCRIPTION_MODELS = [
    "gpt-realtime-whisper",
    "gpt-live-transcribe",
    "gpt-4o-transcribe",
    "whisper-1",
]
AVAILABLE_LANGUAGES = ["auto", "en", "en-US", "de", "es", "fr"]
# Official OpenAI Realtime ephemeral session mint endpoint (not a stored secret value).
OPENAI_REALTIME_SESSION_URL = "https://api.openai.com/v1/realtime/client_secrets"
OPENAI_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
TEMP_AUDIO_TTL_SECONDS = 600


class VoiceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.ai = AiSettingsService(db)
        self.audit = AuditService(db)
        self.storage = StorageService(self.settings)

    def voice_settings_out(self, row: AiRuntimeSettings | None = None) -> VoiceSettingsOut:
        row = row or self.ai.get()
        return VoiceSettingsOut(
            voice_enabled=bool(row.voice_enabled),
            transcription_model=row.transcription_model,
            available_transcription_models=AVAILABLE_TRANSCRIPTION_MODELS,
            voice_language=row.voice_language,
            available_languages=AVAILABLE_LANGUAGES,
            voice_stop_mode=row.voice_stop_mode,  # type: ignore[arg-type]
            silence_timeout_ms=row.silence_timeout_ms,
            max_recording_seconds=row.max_recording_seconds,
            retain_source_audio=bool(row.retain_source_audio),
            retain_corrected_transcript=bool(row.retain_corrected_transcript),
            remote_voice_enabled=bool(row.remote_voice_enabled),
        )

    def update_voice_settings(self, **kwargs: Any) -> VoiceSettingsOut:
        row = self.ai.get()
        if "voice_enabled" in kwargs and kwargs["voice_enabled"] is not None:
            row.voice_enabled = bool(kwargs["voice_enabled"])
        if kwargs.get("transcription_model") is not None:
            model = kwargs["transcription_model"]
            if model not in AVAILABLE_TRANSCRIPTION_MODELS:
                raise AppError(
                    code="invalid_transcription_model",
                    message="Unsupported transcription model",
                    status_code=400,
                )
            row.transcription_model = model
        if kwargs.get("voice_language") is not None:
            lang = kwargs["voice_language"]
            if lang not in AVAILABLE_LANGUAGES:
                raise AppError(
                    code="invalid_voice_language",
                    message="Unsupported voice language",
                    status_code=400,
                )
            row.voice_language = lang
        if kwargs.get("voice_stop_mode") is not None:
            mode = kwargs["voice_stop_mode"]
            if mode not in {"manual", "vad"}:
                raise AppError(
                    code="invalid_voice_stop_mode",
                    message="Stop mode must be manual or vad",
                    status_code=400,
                )
            row.voice_stop_mode = mode
        if kwargs.get("silence_timeout_ms") is not None:
            row.silence_timeout_ms = int(kwargs["silence_timeout_ms"])
        if kwargs.get("max_recording_seconds") is not None:
            row.max_recording_seconds = int(kwargs["max_recording_seconds"])
        if kwargs.get("retain_source_audio") is not None:
            row.retain_source_audio = bool(kwargs["retain_source_audio"])
        if kwargs.get("retain_corrected_transcript") is not None:
            row.retain_corrected_transcript = bool(kwargs["retain_corrected_transcript"])
        if kwargs.get("remote_voice_enabled") is not None:
            # Product default remains false for pilot; allow admin toggle for future.
            row.remote_voice_enabled = bool(kwargs["remote_voice_enabled"])
        self.audit.record(
            event_type="voice.settings_updated",
            message="Voice settings updated",
            actor_type="admin",
            details={
                "voice_enabled": row.voice_enabled,
                "transcription_model": row.transcription_model,
                "retain_source_audio": row.retain_source_audio,
            },
        )
        self.db.flush()
        return self.voice_settings_out(row)

    def create_realtime_session(self, *, actor: str = "admin") -> RealtimeSessionOut:
        row = self.ai.get()
        if not row.voice_enabled:
            raise AppError(
                code="voice_disabled",
                message="Voice transcription is disabled by admin",
                status_code=403,
            )

        session_config = self._session_config(row)
        privacy = self._privacy(row)
        use_mock = (
            self.settings.interview_provider == "mock"
            or row.interview_provider == "mock"
            or not self.settings.openai_api_key
        )

        if use_mock:
            expires = datetime.now(UTC) + timedelta(seconds=60)
            secret = f"ek_mock_{uuid.uuid4().hex}"
            provider: str = "mock"
        else:
            secret, expires, provider = self._mint_live_secret(session_config)

        self.audit.record(
            assessment_id=None,
            event_type="voice.realtime_session_created",
            message="Ephemeral Realtime transcription credentials minted",
            actor_type="admin",
            actor_subject=actor,
            details={
                "provider": provider,
                "transcription_model": row.transcription_model,
                "expires_at": expires.isoformat(),
                # Never log secret or API key.
            },
        )
        self.db.flush()
        return RealtimeSessionOut(
            client_secret=secret,
            expires_at=expires,
            provider=provider,  # type: ignore[arg-type]
            realtime_calls_url=OPENAI_CALLS_URL,
            transcription_model=row.transcription_model,
            language=None if row.voice_language == "auto" else row.voice_language,
            stop_mode=row.voice_stop_mode,  # type: ignore[arg-type]
            silence_timeout_ms=row.silence_timeout_ms,
            max_recording_seconds=row.max_recording_seconds,
            voice_enabled=bool(row.voice_enabled),
            session_config=session_config,
            privacy=privacy,
        )

    def register_temp_audio(self, *, assessment_id: str | None, filename: str) -> TempAudioOut:
        row = self.ai.get()
        self.cleanup_expired()
        expires = datetime.now(UTC) + timedelta(seconds=TEMP_AUDIO_TTL_SECONDS)
        retained = bool(row.retain_source_audio)
        if retained:
            paths = self.storage.ensure_directories()
            directory = paths.uploads / "voice"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid.uuid4().hex}_{Path(filename).name}"
            path.write_bytes(b"")  # placeholder; upload stream can overwrite
            path_str = str(path)
            path_label = f"data/uploads/voice/{path.name}"
        else:
            handle = tempfile.NamedTemporaryFile(
                prefix="sd-voice-",
                suffix=Path(filename).suffix or ".webm",
                delete=False,
                dir=tempfile.gettempdir(),
            )
            handle.write(b"")
            handle.close()
            path_str = handle.name
            path_label = f"tmp/{Path(path_str).name}"

        record = VoiceTempAudio(
            assessment_id=assessment_id,
            path=path_str,
            retained=retained,
            expires_at=expires,
            cleaned_up=False,
        )
        self.db.add(record)
        self.db.flush()
        return TempAudioOut(
            id=record.id,
            path_label=path_label,
            retained=retained,
            expires_at=expires,
            cleaned_up=False,
        )

    def cleanup_temp_audio(self, audio_id: str, *, force: bool = False) -> tuple[bool, bool]:
        record = self.db.scalar(select(VoiceTempAudio).where(VoiceTempAudio.id == audio_id))
        if record is None:
            raise AppError(
                code="voice_audio_not_found", message="Temp audio record not found", status_code=404
            )
        if record.retained and not force:
            # Explicit retention: do not delete unless forced by admin policy change/timeout handling.
            return False, False
        removed = self._remove_file(record.path)
        record.cleaned_up = True
        self.db.flush()
        return True, removed

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
        rows = self.db.scalars(
            select(VoiceTempAudio).where(
                VoiceTempAudio.cleaned_up.is_(False), VoiceTempAudio.expires_at <= now
            )
        ).all()
        count = 0
        for row in rows:
            # Expired retained files are also removed unless still within retention window —
            # TTL applies to temp registration; retained copies use longer window via same TTL for pilot.
            self._remove_file(row.path)
            row.cleaned_up = True
            count += 1
        if count:
            self.db.flush()
        return count

    def _mint_live_secret(self, session_config: dict[str, Any]) -> tuple[str, datetime, str]:
        api_key = self.settings.openai_api_key
        if not api_key:
            raise AppError(
                code="openai_not_configured",
                message="OPENAI_API_KEY is required for live voice",
                status_code=503,
            )
        payload = {
            "expires_after": {"anchor": "created_at", "seconds": 60},
            "session": session_config,
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    OPENAI_REALTIME_SESSION_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                logger.warning(
                    "realtime client_secrets failed status=%s body=%s",
                    response.status_code,
                    redact_secrets(response.text[:300]),
                )
                raise AppError(
                    code="realtime_session_failed",
                    message="Failed to create Realtime transcription credentials",
                    status_code=502,
                )
            data = response.json()
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("realtime client_secrets error type=%s", type(exc).__name__)
            raise AppError(
                code="realtime_session_failed",
                message="Failed to create Realtime transcription credentials",
                status_code=502,
            ) from exc

        secret = data.get("value") or (data.get("client_secret") or {}).get("value")
        expires_raw = data.get("expires_at") or (data.get("client_secret") or {}).get("expires_at")
        if not secret:
            raise AppError(
                code="realtime_session_invalid",
                message="Realtime credentials missing secret",
                status_code=502,
            )
        if isinstance(expires_raw, (int, float)):
            expires = datetime.fromtimestamp(expires_raw, tz=UTC)
        else:
            expires = datetime.now(UTC) + timedelta(seconds=60)
        # Ensure we never accidentally echo the long-lived key.
        if secret == api_key or secret.startswith(api_key[:12]):
            raise AppError(
                code="realtime_session_unsafe",
                message="Refusing to return non-ephemeral credential",
                status_code=500,
            )
        return secret, expires, "live"

    def _session_config(self, row: AiRuntimeSettings) -> dict[str, Any]:
        transcription: dict[str, Any] = {"model": row.transcription_model or "gpt-realtime-whisper"}
        if row.voice_language and row.voice_language != "auto":
            # Prefer ISO-ish short codes for Realtime API.
            lang = row.voice_language.split("-")[0].lower()
            transcription["language"] = lang
        turn_detection: dict[str, Any] | None
        if row.voice_stop_mode == "vad":
            turn_detection = {
                "type": "server_vad",
                "silence_duration_ms": int(row.silence_timeout_ms),
            }
        else:
            turn_detection = None
        return {
            "type": "transcription",
            "audio": {
                "input": {
                    "transcription": transcription,
                    "turn_detection": turn_detection,
                }
            },
        }

    def _privacy(self, row: AiRuntimeSettings) -> VoicePrivacyOut:
        if row.retain_source_audio:
            mode = "retained_upload"
            notice = (
                "Source audio retention is enabled. Audio may be stored under secured upload storage "
                "when explicitly uploaded. Corrected transcripts are retained."
            )
        else:
            mode = "browser_only"
            notice = (
                "Source audio is not retained. Audio streams to OpenAI Realtime via ephemeral WebRTC "
                "credentials and is discarded after transcription. Corrected transcripts are retained by default."
            )
        return VoicePrivacyOut(
            retain_source_audio=bool(row.retain_source_audio),
            retain_corrected_transcript=bool(row.retain_corrected_transcript),
            storage_mode=mode,  # type: ignore[arg-type]
            privacy_notice=notice,
        )

    @staticmethod
    def _remove_file(path: str) -> bool:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                return True
        except OSError:
            logger.warning("failed to remove temp voice file")
        return False
