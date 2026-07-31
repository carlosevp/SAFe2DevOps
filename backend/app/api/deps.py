from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory
from app.core.errors import AppError
from app.services.auth import AdminAuthService


def settings_dep() -> Settings:
    return get_settings()


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def admin_auth_dep(settings: Settings = Depends(settings_dep)) -> AdminAuthService:
    return AdminAuthService(settings)


def require_admin(
    request: Request,
    settings: Settings = Depends(settings_dep),
    auth: AdminAuthService = Depends(admin_auth_dep),
) -> dict[str, str]:
    cookie = request.cookies.get(settings.session_cookie_name)
    return auth.require_admin(cookie)


def require_admin_or_dev_mock(
    request: Request,
    settings: Settings = Depends(settings_dep),
    auth: AdminAuthService = Depends(admin_auth_dep),
) -> dict[str, str]:
    """Allow mock-host access only when explicitly enabled for local/test mock mode."""
    if (
        settings.allow_mock_host_auth
        and settings.integration_provider == "mock"
        and settings.app_env in {"development", "test"}
    ):
        cookie = request.cookies.get(settings.session_cookie_name)
        if cookie:
            try:
                return auth.require_admin(cookie)
            except AppError:
                pass
        return {"role": "admin", "subject": "mock-host"}
    return require_admin(request, settings, auth)
