from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import RemoteContributionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class RemoteInvite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "remote_invites"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="admin")
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="remote_invites")


class RemoteContributor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "remote_contributors"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    invite_token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    assessment: Mapped[Assessment] = relationship(back_populates="remote_contributors")
    contributions: Mapped[list[RemoteContribution]] = relationship(
        back_populates="contributor", cascade="all, delete-orphan"
    )


class RemoteContribution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "remote_contributions"

    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    contributor_id: Mapped[str] = mapped_column(
        ForeignKey("remote_contributors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RemoteContributionStatus.PENDING.value)
    content_trust: Mapped[str] = mapped_column(String(32), nullable=False, default="untrusted")
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attachment_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attachment_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    interview_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    affected_practices_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disposition_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    disposition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    host_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    contributor: Mapped[RemoteContributor] = relationship(back_populates="contributions")
