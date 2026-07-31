from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.schemas.interview import (
    AiSettingsOut,
    AiSettingsUpdate,
    CheckpointOut,
    DraftSaveIn,
    InterviewSessionOut,
    InterviewStartOut,
    TurnSubmitIn,
    TurnSubmitOut,
)
from app.services.ai_settings import AVAILABLE_EFFORTS, AVAILABLE_MODELS, AiSettingsService
from app.services.interview import InterviewService
from app.services.voice import VoiceService

router = APIRouter(tags=["interview"])


@router.post("/assessments/{assessment_id}/interview/start", response_model=InterviewStartOut)
def start_interview(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> InterviewStartOut:
    session = InterviewService(db).start(assessment_id, actor=admin.get("subject", "admin"))
    db.commit()
    return InterviewStartOut(session=session)


@router.get("/assessments/{assessment_id}/interview", response_model=InterviewSessionOut)
def get_interview(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> InterviewSessionOut:
    return InterviewService(db).get_session(assessment_id)


@router.post("/assessments/{assessment_id}/interview/resume", response_model=InterviewSessionOut)
def resume_interview(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> InterviewSessionOut:
    session = InterviewService(db).resume(assessment_id, actor=admin.get("subject", "admin"))
    db.commit()
    return session


@router.post("/assessments/{assessment_id}/interview/save", response_model=InterviewSessionOut)
def save_interview(
    assessment_id: str,
    body: DraftSaveIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> InterviewSessionOut:
    session = InterviewService(db).save_and_exit(
        assessment_id, draft=body.draft_answer_text, actor=admin.get("subject", "admin")
    )
    db.commit()
    return session


@router.put("/assessments/{assessment_id}/interview/draft", response_model=InterviewSessionOut)
def save_draft(
    assessment_id: str,
    body: DraftSaveIn,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> InterviewSessionOut:
    session = InterviewService(db).save_draft(assessment_id, body.draft_answer_text)
    db.commit()
    return session


@router.post("/assessments/{assessment_id}/interview/turns", response_model=TurnSubmitOut)
def submit_turn(
    assessment_id: str,
    body: TurnSubmitIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> TurnSubmitOut:
    result = InterviewService(db).submit_turn(
        assessment_id,
        answer_text=body.answer_text,
        idempotency_key=body.idempotency_key,
        is_clarification=body.is_clarification,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return result


@router.get("/assessments/{assessment_id}/interview/checkpoint", response_model=CheckpointOut)
def interview_checkpoint(
    assessment_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> CheckpointOut:
    return InterviewService(db).checkpoint(assessment_id)


@router.post("/assessments/{assessment_id}/interview/complete", response_model=InterviewSessionOut)
def complete_interview(
    assessment_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> InterviewSessionOut:
    session = InterviewService(db).complete(assessment_id, actor=admin.get("subject", "admin"))
    db.commit()
    return session


def _ai_settings_out(db: Session) -> AiSettingsOut:
    service = AiSettingsService(db)
    row = service.get()
    voice = VoiceService(db).voice_settings_out(row)
    return AiSettingsOut(
        assessment_model=row.assessment_model,
        reasoning_effort=row.reasoning_effort,
        interview_provider=row.interview_provider,  # type: ignore[arg-type]
        transcription_model=voice.live_transcription_model,
        live_transcription_model=voice.live_transcription_model,
        final_transcription_model=voice.final_transcription_model,
        live_delay=voice.live_delay,
        expected_languages=voice.expected_languages,
        company_vocabulary=voice.company_vocabulary,
        final_refinement_enabled=voice.final_refinement_enabled,
        prompt_config_version=service.prompt_config_version(),
        available_models=AVAILABLE_MODELS,
        available_reasoning_efforts=AVAILABLE_EFFORTS,
        available_live_transcription_models=voice.available_live_transcription_models,
        available_final_transcription_models=voice.available_final_transcription_models,
        voice_enabled=bool(row.voice_enabled),
        voice_language=row.voice_language,
        voice_stop_mode=row.voice_stop_mode,  # type: ignore[arg-type]
        silence_timeout_ms=row.silence_timeout_ms,
        max_recording_seconds=row.max_recording_seconds,
        retain_source_audio=bool(row.retain_source_audio),
        retain_corrected_transcript=bool(row.retain_corrected_transcript),
        remote_voice_enabled=bool(row.remote_voice_enabled),
        updated_at=row.updated_at,
    )


@router.get("/ai-settings", response_model=AiSettingsOut)
def get_ai_settings(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AiSettingsOut:
    return _ai_settings_out(db)


@router.put("/ai-settings", response_model=AiSettingsOut)
def update_ai_settings(
    body: AiSettingsUpdate,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AiSettingsOut:
    service = AiSettingsService(db)
    service.update(
        assessment_model=body.assessment_model,
        reasoning_effort=body.reasoning_effort,
        interview_provider=body.interview_provider,
        actor=admin.get("subject", "admin"),
    )
    voice_fields = {
        "transcription_model": body.transcription_model,
        "live_transcription_model": body.live_transcription_model,
        "final_transcription_model": body.final_transcription_model,
        "live_delay": body.live_delay,
        "expected_languages": body.expected_languages,
        "company_vocabulary": body.company_vocabulary,
        "final_refinement_enabled": body.final_refinement_enabled,
        "voice_enabled": body.voice_enabled,
        "voice_language": body.voice_language,
        "voice_stop_mode": body.voice_stop_mode,
        "silence_timeout_ms": body.silence_timeout_ms,
        "max_recording_seconds": body.max_recording_seconds,
        "retain_source_audio": body.retain_source_audio,
        "retain_corrected_transcript": body.retain_corrected_transcript,
        "remote_voice_enabled": body.remote_voice_enabled,
    }
    if any(v is not None for v in voice_fields.values()):
        VoiceService(db).update_voice_settings(**voice_fields)
    db.commit()
    return _ai_settings_out(db)
