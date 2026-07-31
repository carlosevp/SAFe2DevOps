from __future__ import annotations

from fastapi import Response

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import (
    issue_admin_session_token,
    verify_admin_session_token,
    verify_password,
)


class AdminAuthService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def login(self, password: str, response: Response) -> dict[str, str]:
        if not self.settings.admin_password_hash:
            raise AppError(
                code="admin_not_configured",
                message="Admin password hash is not configured",
                status_code=503,
            )
        if not verify_password(password, self.settings.admin_password_hash):
            raise AppError(
                code="invalid_credentials", message="Invalid credentials", status_code=401
            )

        token = issue_admin_session_token(self.settings)
        response.set_cookie(
            key=self.settings.session_cookie_name,
            value=token,
            httponly=True,
            secure=self.settings.is_production,
            samesite="lax",
            max_age=self.settings.session_ttl_seconds,
            path="/",
        )
        return {"status": "authenticated", "role": "admin"}

    def logout(self, response: Response) -> dict[str, str]:
        response.delete_cookie(
            key=self.settings.session_cookie_name,
            path="/",
            httponly=True,
            secure=self.settings.is_production,
            samesite="lax",
        )
        return {"status": "logged_out"}

    def require_admin(self, cookie_value: str | None) -> dict[str, str]:
        if not cookie_value:
            raise AppError(
                code="unauthenticated", message="Authentication required", status_code=401
            )
        try:
            payload = verify_admin_session_token(self.settings, cookie_value)
        except ValueError as exc:
            raise AppError(
                code="unauthenticated", message="Authentication required", status_code=401
            ) from exc
        return {"role": "admin", "subject": str(payload.get("sub", "admin"))}
