from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PublishedReport


class PublicationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def next_version(self, assessment_id: str) -> int:
        current = self.db.scalar(
            select(func.max(PublishedReport.version)).where(PublishedReport.assessment_id == assessment_id)
        )
        return int(current or 0) + 1

    def add(self, report: PublishedReport) -> PublishedReport:
        self.db.add(report)
        self.db.flush()
        return report

    def get(self, report_id: str) -> PublishedReport | None:
        return self.db.get(PublishedReport, report_id)
