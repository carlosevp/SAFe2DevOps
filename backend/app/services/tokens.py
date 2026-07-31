from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import issue_assessment_access_token, verify_assessment_access_token
from app.models.access_token import AccessTokenRevocation


class AssessmentAccessTokenService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def issue(self, *, assessment_id: str, role: str = "participant") -> dict[str, str]:
        token, jti, expires_at = issue_assessment_access_token(
            self.settings,
            assessment_id=assessment_id,
            role=role,
        )
        return {
            "token": token,
            "jti": jti,
            "assessment_id": assessment_id,
            "role": role,
            "expires_at": expires_at.isoformat(),
        }

    def verify(self, db: Session, token: str) -> dict[str, str]:
        try:
            payload = verify_assessment_access_token(self.settings, token)
        except ValueError as exc:
            code = str(exc)
            raise AppError(code=code, message="Assessment access token is not valid", status_code=401) from exc

        jti = str(payload["jti"])
        revoked = db.scalar(select(AccessTokenRevocation).where(AccessTokenRevocation.jti == jti))
        if revoked is not None:
            raise AppError(code="token_revoked", message="Assessment access token has been revoked", status_code=401)

        return {
            "jti": jti,
            "assessment_id": str(payload.get("assessment_id", "")),
            "role": str(payload.get("role", "participant")),
        }

    def revoke(
        self,
        db: Session,
        *,
        jti: str,
        assessment_id: str | None = None,
        reason: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, str]:
        existing = db.get(AccessTokenRevocation, jti)
        if existing is None:
            db.add(
                AccessTokenRevocation(
                    jti=jti,
                    assessment_id=assessment_id,
                    reason=reason,
                    revoked_at=datetime.now(UTC),
                    expires_at=expires_at or datetime.now(UTC),
                )
            )
            db.flush()
        return {"status": "revoked", "jti": jti}
