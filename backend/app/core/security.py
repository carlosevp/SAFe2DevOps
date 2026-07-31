from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import Settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def build_serializer(settings: Settings, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=settings.app_secret_key, salt=salt)


def issue_admin_session_token(settings: Settings, *, subject: str = "admin") -> str:
    serializer = build_serializer(settings, salt="admin-session")
    return serializer.dumps({"sub": subject, "typ": "admin_session"})


def verify_admin_session_token(settings: Settings, token: str) -> dict[str, Any]:
    serializer = build_serializer(settings, salt="admin-session")
    try:
        payload = serializer.loads(token, max_age=settings.session_ttl_seconds)
    except SignatureExpired as exc:
        raise ValueError("session_expired") from exc
    except BadSignature as exc:
        raise ValueError("session_invalid") from exc
    if payload.get("typ") != "admin_session":
        raise ValueError("session_invalid")
    return payload


def issue_assessment_access_token(
    settings: Settings,
    *,
    assessment_id: str,
    role: str = "participant",
    ttl_seconds: int | None = None,
) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at)."""
    jti = secrets.token_urlsafe(16)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds or settings.assessment_token_ttl_seconds)
    serializer = build_serializer(settings, salt="assessment-access")
    token = serializer.dumps(
        {
            "typ": "assessment_access",
            "jti": jti,
            "assessment_id": assessment_id,
            "role": role,
            "exp": int(expires_at.timestamp()),
        }
    )
    return token, jti, expires_at


def verify_assessment_access_token(settings: Settings, token: str) -> dict[str, Any]:
    serializer = build_serializer(settings, salt="assessment-access")
    max_age = settings.assessment_token_ttl_seconds
    try:
        payload = serializer.loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise ValueError("token_expired") from exc
    except BadSignature as exc:
        raise ValueError("token_invalid") from exc
    if payload.get("typ") != "assessment_access" or not payload.get("jti"):
        raise ValueError("token_invalid")
    exp = payload.get("exp")
    if isinstance(exp, int) and exp < int(datetime.now(UTC).timestamp()):
        raise ValueError("token_expired")
    return payload
