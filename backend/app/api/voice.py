from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.schemas.voice import (
    RealtimeSessionOut,
    TempAudioCleanupOut,
    TempAudioOut,
    TempAudioRegisterIn,
    VoiceClientEventIn,
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
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RealtimeSessionOut:
    service = VoiceService(db)
    service.cleanup_expired()
    out = service.create_realtime_session(actor=admin.get("subject", "admin"))
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
