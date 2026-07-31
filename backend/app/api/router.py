from __future__ import annotations

from fastapi import APIRouter

from app.api import assessment_model, assessments, auth, health, integrations, interview, voice

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(assessment_model.router)
api_router.include_router(assessments.router)
api_router.include_router(integrations.router)
api_router.include_router(interview.router)
api_router.include_router(voice.router)
