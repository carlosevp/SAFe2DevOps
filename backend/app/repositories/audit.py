from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditEvent


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, event: AuditEvent) -> AuditEvent:
        self.db.add(event)
        self.db.flush()
        return event
