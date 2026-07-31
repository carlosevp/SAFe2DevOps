from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AssessmentStatus, EvidenceInfluenceMode, ParticipationMode
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.enterprise import (
        AssessmentStandardFinding,
        AssessmentStandardSnapshot,
        AssessmentTechnologyContext,
    )
    from app.models.evidence import EvidenceSnapshot
    from app.models.interview import InterviewTurn
    from app.models.practice import PracticeCoverage
    from app.models.remote import RemoteContributor, RemoteInvite
    from app.models.review import AssessmentReview, ImprovementAction, PublishedReport


class Assessment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessments"

    team_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_service_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_stream: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    evidence_influence_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EvidenceInfluenceMode.BALANCED.value
    )
    participation_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ParticipationMode.HYBRID_REMOTE.value
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AssessmentStatus.SETUP.value
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remote_participation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    source_selection: Mapped[AssessmentSourceSelection | None] = relationship(
        back_populates="assessment", uselist=False, cascade="all, delete-orphan"
    )
    evidence_snapshots: Mapped[list[EvidenceSnapshot]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    interview_turns: Mapped[list[InterviewTurn]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    practice_coverages: Mapped[list[PracticeCoverage]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    remote_invites: Mapped[list[RemoteInvite]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    remote_contributors: Mapped[list[RemoteContributor]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[AssessmentReview]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    improvement_actions: Mapped[list[ImprovementAction]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    published_reports: Mapped[list[PublishedReport]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    technology_context: Mapped[AssessmentTechnologyContext | None] = relationship(
        back_populates="assessment", uselist=False, cascade="all, delete-orphan"
    )
    standard_snapshots: Mapped[list[AssessmentStandardSnapshot]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    standard_findings: Mapped[list[AssessmentStandardFinding]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class AssessmentSourceSelection(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assessment_source_selections"
    __table_args__ = (UniqueConstraint("assessment_id", name="uq_source_selection_assessment"),)

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    jira_project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    jira_project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jira_board_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jira_board_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    jira_jql: Mapped[str | None] = mapped_column(Text, nullable=True)
    ado_project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ado_project_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ado_repository_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ado_repository_name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(200), nullable=False, default="main")
    selected_pipelines_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    assessment: Mapped[Assessment] = relationship(back_populates="source_selection")
