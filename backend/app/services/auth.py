from __future__ import annotations

import secrets

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
        """Authenticate admin with ADMIN_PASSWORD_HASH and/or APP_SECRET_KEY.

        Light login: the shared APP_SECRET_KEY value is accepted as the admin secret
        when configured. A dedicated ADMIN_PASSWORD_HASH remains supported and preferred
        when both are present (either may succeed).
        """
        password = (password or "").strip()
        if not password:
            raise AppError(
                code="invalid_credentials", message="Invalid credentials", status_code=401
            )

        hash_ok = bool(self.settings.admin_password_hash) and verify_password(
            password, self.settings.admin_password_hash
        )
        secret = (self.settings.app_secret_key or "").strip()
        # compare_digest requires equal-length strings; mismatched length is simply not a match.
        secret_ok = bool(secret) and len(password) == len(secret) and secrets.compare_digest(
            password, secret
        )

        if not self.settings.admin_password_hash and not secret:
            raise AppError(
                code="admin_not_configured",
                message="Admin login is not configured (set APP_SECRET_KEY or ADMIN_PASSWORD_HASH)",
                status_code=503,
            )
        if not (hash_ok or secret_ok):
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
