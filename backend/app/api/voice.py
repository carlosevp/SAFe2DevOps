from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.schemas.voice import (
    RealtimeSessionOut,
    TempAudioCleanupOut,
    TempAudioOut,
    TempAudioRegisterIn,
    VoiceSettingsOut,
    VoiceSettingsUpdate,
)
from app.services.voice import VoiceService

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


@router.post("/realtime-call")
async def exchange_realtime_call(
    request: Request,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> PlainTextResponse:
    """Server-mediated WebRTC SDP exchange with OpenAI (keeps API key server-side)."""
    offer = (await request.body()).decode("utf-8", errors="replace")
    service = VoiceService(db)
    answer = service.exchange_realtime_sdp(offer, actor=admin.get("subject", "admin"))
    db.commit()
    return PlainTextResponse(content=answer, media_type="application/sdp")


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
