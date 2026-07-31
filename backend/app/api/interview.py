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


@router.get("/ai-settings", response_model=AiSettingsOut)
def get_ai_settings(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AiSettingsOut:
    service = AiSettingsService(db)
    row = service.get()
    return AiSettingsOut(
        assessment_model=row.assessment_model,
        reasoning_effort=row.reasoning_effort,
        interview_provider=row.interview_provider,  # type: ignore[arg-type]
        transcription_model=row.transcription_model,
        prompt_config_version=service.prompt_config_version(),
        available_models=AVAILABLE_MODELS,
        available_reasoning_efforts=AVAILABLE_EFFORTS,
        updated_at=row.updated_at,
    )


@router.put("/ai-settings", response_model=AiSettingsOut)
def update_ai_settings(
    body: AiSettingsUpdate,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> AiSettingsOut:
    service = AiSettingsService(db)
    row = service.update(
        assessment_model=body.assessment_model,
        reasoning_effort=body.reasoning_effort,
        interview_provider=body.interview_provider,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return AiSettingsOut(
        assessment_model=row.assessment_model,
        reasoning_effort=row.reasoning_effort,
        interview_provider=row.interview_provider,  # type: ignore[arg-type]
        transcription_model=row.transcription_model,
        prompt_config_version=service.prompt_config_version(),
        available_models=AVAILABLE_MODELS,
        available_reasoning_efforts=AVAILABLE_EFFORTS,
        updated_at=row.updated_at,
    )
