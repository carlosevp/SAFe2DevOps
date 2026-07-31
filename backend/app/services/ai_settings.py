from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment_config import get_assessment_model_config
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.ai_settings import AiRuntimeSettings
from app.services.audit import AuditService

AVAILABLE_MODELS = [
    "gpt-5.6-terra",
    "gpt-5.4",
    "gpt-5.3",
    "gpt-4.1",
]
AVAILABLE_EFFORTS = ["low", "medium", "high"]


class AiSettingsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.settings = get_settings()

    def get(self) -> AiRuntimeSettings:
        row = self.db.scalar(
            select(AiRuntimeSettings).where(AiRuntimeSettings.singleton_key == "default")
        )
        if row is None:
            model_cfg = get_assessment_model_config()
            row = AiRuntimeSettings(
                singleton_key="default",
                assessment_model=self.settings.openai_assessment_model
                or model_cfg.model_defaults.assessment_model,
                reasoning_effort=self.settings.openai_reasoning_effort
                or model_cfg.model_defaults.reasoning_effort,
                interview_provider=self.settings.interview_provider,
                transcription_model=self.settings.openai_transcription_model
                or model_cfg.model_defaults.transcription_model,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def update(
        self,
        *,
        assessment_model: str | None = None,
        reasoning_effort: str | None = None,
        interview_provider: str | None = None,
        actor: str = "admin",
    ) -> AiRuntimeSettings:
        row = self.get()
        if assessment_model is not None:
            if assessment_model not in AVAILABLE_MODELS:
                raise AppError(
                    code="invalid_ai_model", message="Unsupported assessment model", status_code=400
                )
            row.assessment_model = assessment_model
        if reasoning_effort is not None:
            if reasoning_effort not in AVAILABLE_EFFORTS:
                raise AppError(
                    code="invalid_reasoning_effort",
                    message="Unsupported reasoning effort",
                    status_code=400,
                )
            row.reasoning_effort = reasoning_effort
        if interview_provider is not None:
            if interview_provider not in {"mock", "live"}:
                raise AppError(
                    code="invalid_interview_provider",
                    message="Provider must be mock or live",
                    status_code=400,
                )
            row.interview_provider = interview_provider
        self.audit.record(
            event_type="ai.settings_updated",
            message="AI runtime settings updated",
            actor_type="admin",
            actor_subject=actor,
            details={
                "assessment_model": row.assessment_model,
                "reasoning_effort": row.reasoning_effort,
                "interview_provider": row.interview_provider,
            },
        )
        self.db.flush()
        return row

    def prompt_config_version(self) -> str:
        cfg = get_assessment_model_config()
        # Version from YAML if present, else stable label.
        version = getattr(cfg, "version", None) or "assessment_model.yaml"
        return str(version)
