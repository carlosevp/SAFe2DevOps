from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings, get_settings
from app.core.db import check_database_ready
from app.schemas.health import LiveResponse, ReadyResponse
from app.services.storage import StorageService

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("/health/ready", response_model=ReadyResponse)
def ready(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ReadyResponse:
    storage = StorageService(settings)
    storage_ok = storage.validate_ready()
    db_ok = check_database_ready(settings)
    checks = {
        "storage": "ok" if storage_ok else "error",
        "database": "ok" if db_ok else "error",
        "storage_labels": storage.paths().as_public_labels() if storage_ok else {},
    }
    healthy = storage_ok and db_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ok" if healthy else "unavailable", checks=checks)
