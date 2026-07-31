from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Assessment, AssessmentSourceSelection, PracticeCoverage


class AssessmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, assessment: Assessment) -> Assessment:
        self.db.add(assessment)
        self.db.flush()
        return assessment

    def get(self, assessment_id: str) -> Assessment | None:
        return self.db.scalar(
            select(Assessment)
            .where(Assessment.id == assessment_id)
            .options(
                selectinload(Assessment.source_selection),
                selectinload(Assessment.practice_coverages),
                selectinload(Assessment.published_reports),
            )
        )

    def list_all(self) -> list[Assessment]:
        return list(self.db.scalars(select(Assessment).order_by(Assessment.created_at.desc())))

    def add_source_selection(
        self, selection: AssessmentSourceSelection
    ) -> AssessmentSourceSelection:
        self.db.add(selection)
        self.db.flush()
        return selection

    def upsert_coverage(self, coverage: PracticeCoverage) -> PracticeCoverage:
        self.db.add(coverage)
        self.db.flush()
        return coverage

    def get_coverage(self, assessment_id: str, practice_key: str) -> PracticeCoverage | None:
        return self.db.scalar(
            select(PracticeCoverage).where(
                PracticeCoverage.assessment_id == assessment_id,
                PracticeCoverage.practice_key == practice_key,
            )
        )
