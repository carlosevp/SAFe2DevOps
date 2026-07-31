from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntegrationConfiguration


class IntegrationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_singleton(self) -> IntegrationConfiguration | None:
        return self.db.scalar(
            select(IntegrationConfiguration).where(
                IntegrationConfiguration.singleton_key == "default"
            )
        )

    def get_or_create_singleton(self) -> IntegrationConfiguration:
        existing = self.get_singleton()
        if existing is not None:
            return existing
        record = IntegrationConfiguration(singleton_key="default")
        self.db.add(record)
        self.db.flush()
        return record
