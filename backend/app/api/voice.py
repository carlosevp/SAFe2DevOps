from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.core.config import get_settings
from app.schemas.voice import (
    RealtimeSessionIn,
    RealtimeSessionOut,
    RefineTranscriptOut,
    TempAudioCleanupOut,
    TempAudioOut,
    TempAudioRegisterIn,
    VoiceClientEventIn,
    VoiceDiagnosticsOut,
    VoiceMetricsIn,
    VoiceSettingsOut,
    VoiceSettingsUpdate,
)
from app.services.voice import VoiceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/settings", response_model=VoiceSettingsOut)
def get_voice_settings(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> VoiceSettingsOut:
    return VoiceService(db).voice_settings_out()


@router.put("/settings", response_model=VoiceSettingsOut)
def update_voice_settings(
    body: VoiceSettingsUpdate,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> VoiceSettingsOut:
    out = VoiceService(db).update_voice_settings(**body.model_dump(exclude_unset=True))
    db.commit()
    return out


@router.post("/realtime-session", response_model=RealtimeSessionOut)
def create_realtime_session(
    body: RealtimeSessionIn | None = None,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RealtimeSessionOut:
    service = VoiceService(db)
    service.cleanup_expired()
    payload = body or RealtimeSessionIn()
    out = service.create_realtime_session(
        actor=admin.get("subject", "admin"),
        assessment_id=payload.assessment_id,
        topic_label=payload.topic_label,
    )
    db.commit()
    return out


@router.post("/refine", response_model=RefineTranscriptOut)
async def refine_transcript(
    audio: UploadFile = File(...),
    assessment_id: str | None = Form(default=None),
    live_transcript: str = Form(default=""),
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RefineTranscriptOut:
    raw = await audio.read()
    service = VoiceService(db)
    out = service.refine_audio(
        file_bytes=raw,
        filename=audio.filename or "capture.webm",
        content_type=audio.content_type,
        assessment_id=assessment_id,
        live_transcript=live_transcript,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return out


@router.post("/client-events")
def voice_client_events(
    body: VoiceClientEventIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
) -> dict[str, str]:
    """Accept browser voice failures so they appear in Railway logs."""
    logger.warning(
        "voice client event stage=%s name=%s message=%s secure_context=%s in_iframe=%s actor=%s ua=%s",
        body.stage,
        body.name,
        body.message,
        body.secure_context,
        body.in_iframe,
        admin.get("subject", "admin"),
        (body.user_agent or "")[:120],
    )
    return {"status": "logged"}


@router.post("/metrics", response_model=VoiceDiagnosticsOut)
def record_voice_metrics(
    body: VoiceMetricsIn,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> VoiceDiagnosticsOut:
    out = VoiceService(db).record_metrics(body)
    db.commit()
    return out


@router.get("/diagnostics", response_model=VoiceDiagnosticsOut)
def get_voice_diagnostics(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> VoiceDiagnosticsOut:
    return VoiceService(db).diagnostics_out()


@router.get("/diagnostics/detail")
def get_voice_diagnostics_detail(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
) -> dict[str, object]:
    """Dev-oriented detail flag. Does not return transcripts; clients keep those locally."""
    settings = get_settings()
    enabled = bool(getattr(settings, "environment", "development") != "production")
    if hasattr(settings, "app_env"):
        enabled = str(getattr(settings, "app_env", "")).lower() not in {"production", "prod"}
    return {
        "detailed_transcript_diagnostics_enabled": enabled,
        "note": "Detailed live/completed/refined transcript views stay in the browser in development only.",
    }


@router.post("/audio/temp", response_model=TempAudioOut)
def register_temp_audio(
    body: TempAudioRegisterIn,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> TempAudioOut:
    out = VoiceService(db).register_temp_audio(
        assessment_id=body.assessment_id, filename=body.filename
    )
    db.commit()
    return out


@router.delete("/audio/{audio_id}", response_model=TempAudioCleanupOut)
def cleanup_temp_audio(
    audio_id: str,
    force: bool = False,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> TempAudioCleanupOut:
    cleaned, removed = VoiceService(db).cleanup_temp_audio(audio_id, force=force)
    db.commit()
    return TempAudioCleanupOut(id=audio_id, cleaned_up=cleaned or removed, removed=removed)
