from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.openai.live import LiveInterviewProvider
from app.openai.mock import MockInterviewProvider
from app.schemas.interview import InterviewAnalysisAI, OpeningQuestionAI
from app.services.ai_settings import AiSettingsService


class InterviewProvider(Protocol):
    name: str

    def generate_opening_question(self, context: dict) -> tuple[OpeningQuestionAI, dict]: ...

    def analyze_answer(self, context: dict) -> tuple[InterviewAnalysisAI, dict]: ...


def get_interview_provider(db: Session, settings: Settings | None = None) -> InterviewProvider:
    settings = settings or get_settings()
    runtime = AiSettingsService(db).get()
    mode = (runtime.interview_provider or settings.interview_provider or "mock").lower()
    if mode == "live":
        return LiveInterviewProvider(
            api_key=settings.openai_api_key,
            model=runtime.assessment_model or settings.openai_assessment_model,
            reasoning_effort=runtime.reasoning_effort or settings.openai_reasoning_effort,
        )
    return MockInterviewProvider()
