from __future__ import annotations

import json
import logging
import os
import tempfile
import time
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
from app.models.ai_settings import AiRuntimeSettings, VoiceDiagnosticsCounters, VoiceTempAudio
from app.schemas.voice import (
    RealtimeSessionOut,
    RefineTranscriptOut,
    TempAudioOut,
    VoiceDiagnosticsOut,
    VoiceMetricsIn,
    VoicePrivacyOut,
    VoiceSettingsOut,
)
from app.services.ai_settings import AiSettingsService
from app.services.audit import AuditService
from app.services.storage import StorageService
from app.services.transcription_context import (
    TranscriptionContextService,
    context_as_dict,
    sanitize_keywords,
)

logger = logging.getLogger(__name__)

AVAILABLE_LIVE_TRANSCRIPTION_MODELS = [
    "gpt-live-transcribe",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "gpt-realtime-whisper",
    "whisper-1",
]
AVAILABLE_FINAL_TRANSCRIPTION_MODELS = [
    "gpt-transcribe",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "whisper-1",
]
# Backward-compatible union shown in older UI fields.
AVAILABLE_TRANSCRIPTION_MODELS = list(
    dict.fromkeys(AVAILABLE_LIVE_TRANSCRIPTION_MODELS + AVAILABLE_FINAL_TRANSCRIPTION_MODELS)
)
DEFAULT_LIVE_MODEL = "gpt-live-transcribe"
DEFAULT_FINAL_MODEL = "gpt-transcribe"
LIVE_DELAYS = ("minimal", "low", "medium", "high", "xhigh")
MODELS_WITHOUT_TURN_DETECTION = frozenset({"gpt-realtime-whisper", "whisper-1", "gpt-live-transcribe"})
AVAILABLE_LANGUAGES = ["auto", "en", "en-US", "de", "es", "fr"]
OPENAI_REALTIME_SESSION_URL = "https://api.openai.com/v1/realtime/client_secrets"
OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
OPENAI_AUDIO_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
TEMP_AUDIO_TTL_SECONDS = 600
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _openai_error_message(body: str) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            message = str(err.get("message") or "").strip()
            if message:
                return message[:240]
        if isinstance(err, str) and err.strip():
            return err.strip()[:240]
    except Exception:  # noqa: BLE001
        pass
    return redact_secrets(text[:240])


class VoiceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.ai = AiSettingsService(db)
        self.audit = AuditService(db)
        self.storage = StorageService(self.settings)
        self.context = TranscriptionContextService(db)

    def voice_settings_out(self, row: AiRuntimeSettings | None = None) -> VoiceSettingsOut:
        row = row or self.ai.get()
        live_model = row.live_transcription_model or row.transcription_model or DEFAULT_LIVE_MODEL
        return VoiceSettingsOut(
            voice_enabled=bool(row.voice_enabled),
            transcription_model=live_model,
            live_transcription_model=live_model,
            final_transcription_model=row.final_transcription_model or DEFAULT_FINAL_MODEL,
            available_live_transcription_models=AVAILABLE_LIVE_TRANSCRIPTION_MODELS,
            available_final_transcription_models=AVAILABLE_FINAL_TRANSCRIPTION_MODELS,
            available_transcription_models=AVAILABLE_TRANSCRIPTION_MODELS,
            live_delay=row.live_delay if row.live_delay in LIVE_DELAYS else "low",  # type: ignore[arg-type]
            expected_languages=self._parse_json_list(row.expected_languages_json) or ["en"],
            company_vocabulary=self._parse_json_list(row.company_vocabulary_json),
            final_refinement_enabled=bool(row.final_refinement_enabled),
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

        live_model = kwargs.get("live_transcription_model") or kwargs.get("transcription_model")
        if live_model is not None:
            if live_model not in AVAILABLE_LIVE_TRANSCRIPTION_MODELS:
                # Allow legacy models that still appear in the union list.
                if live_model not in AVAILABLE_TRANSCRIPTION_MODELS:
                    raise AppError(
                        code="invalid_transcription_model",
                        message="Unsupported live transcription model",
                        status_code=400,
                    )
            row.live_transcription_model = live_model
            row.transcription_model = live_model

        if kwargs.get("final_transcription_model") is not None:
            model = kwargs["final_transcription_model"]
            if model not in AVAILABLE_FINAL_TRANSCRIPTION_MODELS:
                raise AppError(
                    code="invalid_final_transcription_model",
                    message="Unsupported final transcription model",
                    status_code=400,
                )
            row.final_transcription_model = model

        if kwargs.get("live_delay") is not None:
            delay = kwargs["live_delay"]
            if delay not in LIVE_DELAYS:
                raise AppError(
                    code="invalid_live_delay",
                    message="Live delay must be minimal, low, medium, high, or xhigh",
                    status_code=400,
                )
            row.live_delay = delay

        if kwargs.get("expected_languages") is not None:
            langs = [str(x).split("-")[0].lower() for x in kwargs["expected_languages"] if str(x).strip()]
            if not langs:
                langs = ["en"]
            row.expected_languages_json = json.dumps(langs[:6])
            row.voice_language = langs[0]

        if kwargs.get("company_vocabulary") is not None:
            cleaned = sanitize_keywords([str(x) for x in kwargs["company_vocabulary"]])
            row.company_vocabulary_json = json.dumps(cleaned)

        if kwargs.get("final_refinement_enabled") is not None:
            row.final_refinement_enabled = bool(kwargs["final_refinement_enabled"])

        if kwargs.get("voice_language") is not None and kwargs.get("expected_languages") is None:
            lang = kwargs["voice_language"]
            if lang not in AVAILABLE_LANGUAGES:
                raise AppError(
                    code="invalid_voice_language",
                    message="Unsupported voice language",
                    status_code=400,
                )
            row.voice_language = lang
            if lang != "auto":
                row.expected_languages_json = json.dumps([lang.split("-")[0].lower()])

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
            row.remote_voice_enabled = bool(kwargs["remote_voice_enabled"])

        self.audit.record(
            event_type="voice.settings_updated",
            message="Voice settings updated",
            actor_type="admin",
            details={
                "voice_enabled": row.voice_enabled,
                "live_transcription_model": row.live_transcription_model,
                "final_transcription_model": row.final_transcription_model,
                "live_delay": row.live_delay,
                "retain_source_audio": row.retain_source_audio,
                "final_refinement_enabled": row.final_refinement_enabled,
            },
        )
        self.db.flush()
        return self.voice_settings_out(row)

    def create_realtime_session(
        self,
        *,
        actor: str = "admin",
        assessment_id: str | None = None,
        topic_label: str | None = None,
    ) -> RealtimeSessionOut:
        """Mint ephemeral Realtime credentials for browser WebRTC.

        The long-lived OPENAI_API_KEY stays server-side. The browser POSTs its SDP
        offer directly to OpenAI `/v1/realtime/calls` with the ephemeral key.
        """
        row = self.ai.get()
        if not row.voice_enabled:
            raise AppError(
                code="voice_disabled",
                message="Voice transcription is disabled by admin",
                status_code=403,
            )

        ctx = self.context.build_for_assessment(
            assessment_id, settings=row, topic_label=topic_label
        )
        session_config = self._session_config(row, ctx.prompt, ctx.keywords, ctx.languages)
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

        live_model = (
            session_config.get("audio", {})
            .get("input", {})
            .get("transcription", {})
            .get("model", DEFAULT_LIVE_MODEL)
        )
        self.audit.record(
            assessment_id=assessment_id,
            event_type="voice.realtime_session_created",
            message="Ephemeral Realtime transcription credentials minted",
            actor_type="admin",
            actor_subject=actor,
            details={
                "provider": provider,
                "transcription_model": live_model,
                "connection": "ephemeral_webrtc",
                "expires_at": expires.isoformat(),
                "keyword_count": len(ctx.keywords),
            },
        )
        self.db.flush()
        return RealtimeSessionOut(
            client_secret=secret,
            expires_at=expires,
            provider=provider,  # type: ignore[arg-type]
            realtime_calls_url=OPENAI_REALTIME_CALLS_URL,
            transcription_model=live_model,
            live_transcription_model=live_model,
            final_transcription_model=row.final_transcription_model or DEFAULT_FINAL_MODEL,
            live_delay=row.live_delay or "low",
            languages=ctx.languages,
            language=ctx.languages[0] if ctx.languages else None,
            stop_mode="manual",  # type: ignore[arg-type]
            silence_timeout_ms=row.silence_timeout_ms,
            max_recording_seconds=row.max_recording_seconds,
            voice_enabled=bool(row.voice_enabled),
            final_refinement_enabled=bool(row.final_refinement_enabled),
            session_config=session_config,
            transcription_context=context_as_dict(ctx),
            privacy=privacy,
        )

    def refine_audio(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
        assessment_id: str | None,
        live_transcript: str,
        actor: str = "admin",
    ) -> RefineTranscriptOut:
        row = self.ai.get()
        if not row.voice_enabled:
            raise AppError(
                code="voice_disabled",
                message="Voice transcription is disabled by admin",
                status_code=403,
            )
        if not file_bytes:
            raise AppError(code="empty_audio", message="Audio upload was empty", status_code=400)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise AppError(
                code="audio_too_large",
                message="Audio upload exceeds the 25MB limit",
                status_code=413,
            )

        if not row.final_refinement_enabled:
            return RefineTranscriptOut(
                transcript=live_transcript,
                model=row.final_transcription_model or DEFAULT_FINAL_MODEL,
                used_live_fallback=True,
                refined=False,
                warning="Final refinement is disabled. Live draft retained.",
            )

        ctx = self.context.build_for_assessment(assessment_id, settings=row)
        audio_id: str | None = None
        path: Path | None = None
        retained = bool(row.retain_source_audio)
        started = time.perf_counter()
        try:
            audio_id, path = self._store_upload_bytes(
                file_bytes,
                filename=filename or "capture.webm",
                assessment_id=assessment_id,
                retained=retained,
            )
            use_mock = (
                self.settings.interview_provider == "mock"
                or row.interview_provider == "mock"
                or not self.settings.openai_api_key
            )
            model = row.final_transcription_model or DEFAULT_FINAL_MODEL
            if use_mock:
                text = live_transcript.strip() or (
                    "Mock refined transcript: pipeline runs unit tests on every pull request."
                )
            else:
                text = self._transcribe_file(
                    path=path,
                    filename=filename or "capture.webm",
                    content_type=content_type,
                    model=model,
                    prompt=ctx.prompt,
                    keywords=ctx.keywords,
                    languages=ctx.languages,
                )
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.audit.record(
                assessment_id=assessment_id,
                event_type="voice.final_transcription",
                message="Final transcription completed",
                actor_type="admin",
                actor_subject=actor,
                details={
                    "model": model,
                    "duration_ms": duration_ms,
                    "audio_bytes": len(file_bytes),
                    "retained": retained,
                    "keyword_count": len(ctx.keywords),
                },
            )
            if not retained and audio_id:
                self.cleanup_temp_audio(audio_id, force=True)
                audio_id = None
            self.db.flush()
            return RefineTranscriptOut(
                transcript=text.strip(),
                model=model,
                used_live_fallback=False,
                audio_id=audio_id,
                retained=retained,
                refined=True,
                duration_ms=duration_ms,
            )
        except AppError as exc:
            if audio_id and not retained:
                try:
                    self.cleanup_temp_audio(audio_id, force=True)
                except AppError:
                    pass
            self.record_metrics(
                VoiceMetricsIn(refinement_failed=True, final_model=row.final_transcription_model)
            )
            logger.warning("voice refine failed code=%s", exc.code)
            return RefineTranscriptOut(
                transcript=live_transcript,
                model=row.final_transcription_model or DEFAULT_FINAL_MODEL,
                used_live_fallback=True,
                refined=False,
                warning=exc.message or "Final transcription failed. Live draft retained.",
            )
        except Exception as exc:  # noqa: BLE001
            if audio_id and not retained:
                try:
                    self.cleanup_temp_audio(audio_id, force=True)
                except AppError:
                    pass
            self.record_metrics(
                VoiceMetricsIn(refinement_failed=True, final_model=row.final_transcription_model)
            )
            logger.warning("voice refine error type=%s", type(exc).__name__)
            return RefineTranscriptOut(
                transcript=live_transcript,
                model=row.final_transcription_model or DEFAULT_FINAL_MODEL,
                used_live_fallback=True,
                refined=False,
                warning="Final transcription failed. Live draft retained.",
            )

    def _store_upload_bytes(
        self,
        file_bytes: bytes,
        *,
        filename: str,
        assessment_id: str | None,
        retained: bool,
    ) -> tuple[str, Path]:
        self.cleanup_expired()
        expires = datetime.now(UTC) + timedelta(seconds=TEMP_AUDIO_TTL_SECONDS)
        safe_name = Path(filename).name or "capture.webm"
        if retained:
            paths = self.storage.ensure_directories()
            directory = paths.uploads / "voice"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid.uuid4().hex}_{safe_name}"
            path.write_bytes(file_bytes)
            path_label = f"data/uploads/voice/{path.name}"
        else:
            handle = tempfile.NamedTemporaryFile(
                prefix="sd-voice-",
                suffix=Path(safe_name).suffix or ".webm",
                delete=False,
            )
            handle.write(file_bytes)
            handle.close()
            path = Path(handle.name)
            path_label = f"tmp/{path.name}"

        record = VoiceTempAudio(
            assessment_id=assessment_id,
            path=str(path),
            retained=retained,
            expires_at=expires,
            cleaned_up=False,
        )
        self.db.add(record)
        self.db.flush()
        logger.info(
            "voice temp audio stored id=%s retained=%s bytes=%s path_label=%s",
            record.id,
            retained,
            len(file_bytes),
            path_label,
        )
        return record.id, path

    def _transcribe_file(
        self,
        *,
        path: Path,
        filename: str,
        content_type: str | None,
        model: str,
        prompt: str,
        keywords: list[str],
        languages: list[str],
    ) -> str:
        api_key = self.settings.openai_api_key
        if not api_key:
            raise AppError(
                code="openai_not_configured",
                message="OPENAI_API_KEY is required for final transcription",
                status_code=503,
            )

        attempts: list[tuple[str, list[tuple[str, str]]]] = []
        clean_keywords = sanitize_keywords(keywords)[:40]
        langs = [str(x).split("-")[0].lower() for x in languages if str(x).strip()][:6] or ["en"]
        short_prompt = (prompt or "").strip()[:900]

        if model == "gpt-transcribe":
            rich: list[tuple[str, str]] = [("model", model), ("response_format", "json")]
            if short_prompt:
                rich.append(("prompt", short_prompt))
            for lang in langs:
                rich.append(("languages", lang))
            for kw in clean_keywords:
                rich.append(("keywords", kw))
            attempts.append(("gpt-transcribe+context", rich))
            attempts.append(
                ("gpt-transcribe+minimal", [("model", model), ("response_format", "json")])
            )
            # Fallback if the account/model snapshot rejects gpt-transcribe fields.
            legacy: list[tuple[str, str]] = [
                ("model", "gpt-4o-transcribe"),
                ("response_format", "json"),
                ("language", langs[0]),
            ]
            if short_prompt:
                legacy.append(("prompt", short_prompt))
            attempts.append(("gpt-4o-transcribe+context", legacy))
        else:
            form: list[tuple[str, str]] = [("model", model), ("response_format", "json")]
            if langs:
                form.append(("language", langs[0]))
            if short_prompt:
                form.append(("prompt", short_prompt))
            attempts.append((f"{model}+context", form))
            attempts.append((f"{model}+minimal", [("model", model), ("response_format", "json")]))

        mime = content_type or "application/octet-stream"
        last_detail = ""
        with httpx.Client(timeout=120.0) as client:
            for label, form_data in attempts:
                with path.open("rb") as handle:
                    response = client.post(
                        OPENAI_AUDIO_TRANSCRIPTIONS_URL,
                        headers={"Authorization": f"Bearer {api_key}"},
                        data=form_data,
                        files={"file": (filename or path.name, handle, mime)},
                    )
                if response.status_code >= 400:
                    last_detail = _openai_error_message(response.text)
                    logger.warning(
                        "audio transcriptions failed attempt=%s status=%s body=%s",
                        label,
                        response.status_code,
                        redact_secrets(response.text[:400]),
                    )
                    continue
                try:
                    payload = response.json()
                    text = payload.get("text") if isinstance(payload, dict) else None
                    if isinstance(text, str) and text.strip():
                        logger.info("audio transcriptions succeeded attempt=%s", label)
                        return text
                except Exception:  # noqa: BLE001
                    pass
                body = response.text.strip()
                if body and not body.startswith("{"):
                    logger.info("audio transcriptions succeeded attempt=%s text_body", label)
                    return body
                last_detail = "Final transcription returned empty text"

        raise AppError(
            code="final_transcription_failed",
            message=last_detail or "Final transcription failed",
            status_code=502,
        )

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
        logger.info(
            "voice realtime client_secrets mint starting model=%s",
            session_config.get("audio", {}).get("input", {}).get("transcription", {}).get("model"),
        )
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
                detail = _openai_error_message(response.text)
                logger.warning(
                    "realtime client_secrets failed status=%s body=%s",
                    response.status_code,
                    redact_secrets(response.text[:500]),
                )
                raise AppError(
                    code="realtime_session_failed",
                    message=detail or "Failed to create Realtime transcription credentials",
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
        if secret == api_key or secret.startswith(api_key[:12]):
            raise AppError(
                code="realtime_session_unsafe",
                message="Refusing to return non-ephemeral credential",
                status_code=500,
            )
        logger.info("voice realtime client_secrets mint succeeded")
        return secret, expires, "live"

    def register_temp_audio(self, *, assessment_id: str | None, filename: str) -> TempAudioOut:
        """Legacy register endpoint — creates an empty placeholder path."""
        row = self.ai.get()
        self.cleanup_expired()
        expires = datetime.now(UTC) + timedelta(seconds=TEMP_AUDIO_TTL_SECONDS)
        retained = bool(row.retain_source_audio)
        if retained:
            paths = self.storage.ensure_directories()
            directory = paths.uploads / "voice"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid.uuid4().hex}_{Path(filename).name}"
            path.touch()
            path_label = f"data/uploads/voice/{path.name}"
        else:
            handle = tempfile.NamedTemporaryFile(
                prefix="sd-voice-",
                suffix=Path(filename).suffix or ".webm",
                delete=False,
            )
            handle.close()
            path = Path(handle.name)
            path_label = f"tmp/{path.name}"

        record = VoiceTempAudio(
            assessment_id=assessment_id,
            path=str(path),
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
        record = self.db.get(VoiceTempAudio, audio_id)
        if record is None:
            raise AppError(
                code="voice_audio_not_found", message="Temp audio record not found", status_code=404
            )
        if record.cleaned_up:
            return True, False
        if record.retained and not force:
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
            self._remove_file(row.path)
            row.cleaned_up = True
            count += 1
        if count:
            self.db.flush()
        return count

    def record_metrics(self, body: VoiceMetricsIn) -> VoiceDiagnosticsOut:
        row = self._diagnostics_row()
        row.session_count += 1 if body.connection_duration_ms is not None else 0
        if body.connection_duration_ms is not None:
            row.connection_duration_ms_total += int(body.connection_duration_ms)
            if body.connection_duration_ms and row.session_count == 0:
                row.session_count = 1
        if body.time_to_first_delta_ms is not None:
            row.time_to_first_delta_ms_total += int(body.time_to_first_delta_ms)
            row.time_to_first_delta_count += 1
        if body.recording_duration_ms is not None:
            row.recording_duration_ms_total += int(body.recording_duration_ms)
        if body.refine_duration_ms is not None:
            row.refine_duration_ms_total += int(body.refine_duration_ms)
            row.refine_count += 1
        if body.transcript_item_count is not None:
            row.transcript_item_count += int(body.transcript_item_count)
        if body.empty_transcript:
            row.empty_transcript_count += 1
        if body.refinement_failed:
            row.refinement_failure_count += 1
        if body.webrtc_reconnect:
            row.webrtc_reconnect_count += 1
        if body.mic_permission_failure:
            row.mic_permission_failure_count += 1
        if body.device_label:
            row.last_device_label = body.device_label[:200]
        if body.live_model:
            row.live_model = body.live_model[:120]
        if body.final_model:
            row.final_model = body.final_model[:120]
        self.db.flush()
        return self.diagnostics_out()

    def diagnostics_out(self) -> VoiceDiagnosticsOut:
        row = self._diagnostics_row()
        settings = self.ai.get()

        def avg(total: int, count: int) -> float | None:
            if count <= 0:
                return None
            return round(total / count, 1)

        refine_count = max(row.refine_count, 0)
        failure_rate = None
        if refine_count + row.refinement_failure_count > 0:
            denom = refine_count + row.refinement_failure_count
            failure_rate = round(row.refinement_failure_count / denom, 3)

        return VoiceDiagnosticsOut(
            session_count=row.session_count,
            avg_connection_duration_ms=avg(row.connection_duration_ms_total, row.session_count),
            avg_time_to_first_delta_ms=avg(
                row.time_to_first_delta_ms_total, row.time_to_first_delta_count
            ),
            avg_recording_duration_ms=avg(row.recording_duration_ms_total, max(row.session_count, 1)),
            avg_refine_duration_ms=avg(row.refine_duration_ms_total, row.refine_count),
            transcript_item_count=row.transcript_item_count,
            empty_transcript_count=row.empty_transcript_count,
            refinement_failure_count=row.refinement_failure_count,
            webrtc_reconnect_count=row.webrtc_reconnect_count,
            mic_permission_failure_count=row.mic_permission_failure_count,
            refinement_failure_rate=failure_rate,
            live_model=row.live_model or settings.live_transcription_model or DEFAULT_LIVE_MODEL,
            final_model=row.final_model
            or settings.final_transcription_model
            or DEFAULT_FINAL_MODEL,
            last_device_label=row.last_device_label,
        )

    def _diagnostics_row(self) -> VoiceDiagnosticsCounters:
        row = self.db.scalar(
            select(VoiceDiagnosticsCounters).where(VoiceDiagnosticsCounters.singleton_key == "default")
        )
        if row is None:
            row = VoiceDiagnosticsCounters(singleton_key="default")
            self.db.add(row)
            self.db.flush()
        return row

    def _session_config(
        self,
        row: AiRuntimeSettings,
        _prompt: str,
        _keywords: list[str],
        languages: list[str],
    ) -> dict[str, Any]:
        """Build Realtime transcription session config for credential minting.

        Do not include prompt/keywords here — several models reject them on mint
        with "The 'prompt' parameter is not supported for this model". Assessment
        context is returned separately and applied by the browser via session.update
        after the data channel opens (gpt-live-transcribe only).
        """
        model = row.live_transcription_model or row.transcription_model or DEFAULT_LIVE_MODEL
        if model not in AVAILABLE_LIVE_TRANSCRIPTION_MODELS:
            model = DEFAULT_LIVE_MODEL

        transcription: dict[str, Any] = {"model": model}
        if model == "gpt-live-transcribe":
            transcription["languages"] = languages or ["en"]
            transcription["delay"] = row.live_delay if row.live_delay in LIVE_DELAYS else "low"
        elif languages:
            transcription["language"] = languages[0]
        elif row.voice_language and row.voice_language != "auto":
            transcription["language"] = row.voice_language.split("-")[0].lower()

        input_cfg: dict[str, Any] = {
            "transcription": transcription,
            "noise_reduction": {"type": "far_field"},
        }
        # gpt-live-transcribe: turn_detection null so natural pauses do not end the answer.
        if model == "gpt-live-transcribe" or row.voice_stop_mode == "manual":
            input_cfg["turn_detection"] = None
        elif (
            row.voice_stop_mode == "vad"
            and model not in MODELS_WITHOUT_TURN_DETECTION
        ):
            input_cfg["turn_detection"] = {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": max(200, int(row.silence_timeout_ms)),
            }

        return {
            "type": "transcription",
            "audio": {"input": input_cfg},
        }

    def _privacy(self, row: AiRuntimeSettings) -> VoicePrivacyOut:
        if row.retain_source_audio:
            mode = "retained_upload"
            notice = (
                "Source audio retention is enabled. Audio uploaded for final refinement may be stored "
                "under secured upload storage. Corrected transcripts are retained."
            )
        else:
            mode = "browser_only"
            notice = (
                "Source audio is not retained. Live audio streams to OpenAI Realtime via ephemeral WebRTC. "
                "A temporary browser recording is uploaded once for final refinement and deleted immediately. "
                "Corrected transcripts are retained by default."
            )
        return VoicePrivacyOut(
            retain_source_audio=bool(row.retain_source_audio),
            retain_corrected_transcript=bool(row.retain_corrected_transcript),
            storage_mode=mode,  # type: ignore[arg-type]
            privacy_notice=notice,
        )

    @staticmethod
    def _parse_json_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(x).strip() for x in data if str(x).strip()]

    @staticmethod
    def _remove_file(path: str) -> bool:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                return True
        except OSError:
            logger.warning("failed to remove temp voice file")
        return False
