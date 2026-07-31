from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.auth import AdminLoginRequest, AdminMeResponse, AdminSessionResponse
from app.services.auth import AdminAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_service(settings: Settings = Depends(get_settings)) -> AdminAuthService:
    return AdminAuthService(settings)


@router.post("/admin/login", response_model=AdminSessionResponse)
def admin_login(
    body: AdminLoginRequest,
    response: Response,
    auth: AdminAuthService = Depends(_auth_service),
) -> AdminSessionResponse:
    result = auth.login(body.password, response)
    return AdminSessionResponse(**result)


@router.post("/admin/logout", response_model=AdminSessionResponse)
def admin_logout(
    response: Response,
    auth: AdminAuthService = Depends(_auth_service),
) -> AdminSessionResponse:
    result = auth.logout(response)
    return AdminSessionResponse(**result)


@router.get("/admin/me", response_model=AdminMeResponse)
def admin_me(
    request: Request,
    settings: Settings = Depends(get_settings),
    auth: AdminAuthService = Depends(_auth_service),
) -> AdminMeResponse:
    cookie = request.cookies.get(settings.session_cookie_name)
    try:
        session = auth.require_admin(cookie)
    except AppError:
        return AdminMeResponse(authenticated=False)
    return AdminMeResponse(authenticated=True, role=session.get("role"), subject=session.get("subject"))
