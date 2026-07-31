from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import RemoteContributionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


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
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RemoteContributionStatus.PENDING.value)
    content_trust: Mapped[str] = mapped_column(String(32), nullable=False, default="untrusted")

    contributor: Mapped[RemoteContributor] = relationship(back_populates="contributions")
