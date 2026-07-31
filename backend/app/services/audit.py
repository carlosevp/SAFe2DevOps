from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import redact_secrets
from app.models import AuditEvent
from app.models.enums import AuditActorType
from app.repositories.audit import AuditRepository


class AuditService:
    SENSITIVE_KEYS = {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "pat",
        "jira_api_token",
        "ado_pat",
        "encrypted",
    }

    def __init__(self, db: Session) -> None:
        self.repo = AuditRepository(db)

    def record(
        self,
        *,
        event_type: str,
        message: str,
        assessment_id: str | None = None,
        actor_type: AuditActorType | str = AuditActorType.SYSTEM,
        actor_subject: str | None = None,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        cleaned = self.redact_details(details or {})
        event = AuditEvent(
            assessment_id=assessment_id,
            actor_type=str(actor_type),
            actor_subject=actor_subject,
            event_type=event_type,
            message=str(redact_secrets(message)),
            details_json=json.dumps(cleaned, separators=(",", ":")),
            request_id=request_id,
        )
        return self.repo.add(event)

    def redact_details(self, details: dict[str, Any]) -> dict[str, Any]:
        redacted = redact_secrets(details)
        if not isinstance(redacted, dict):
            return {}
        return {
            key: ("***REDACTED***" if self._sensitive(key) else value)
            for key, value in redacted.items()
        }

    def _sensitive(self, key: str) -> bool:
        lowered = key.lower()
        return any(part in lowered for part in self.SENSITIVE_KEYS)
