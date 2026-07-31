from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RemoteSettingsOut(StrictSchema):
    assessment_id: str
    remote_participation_enabled: bool
    active_invite: "RemoteInviteOut | None" = None
    pending_count: int = 0


class RemoteSettingsUpdate(StrictSchema):
    remote_participation_enabled: bool


class RemoteInviteOut(StrictSchema):
    jti: str
    invite_url: str
    expires_at: datetime
    revoked: bool = False
    created_at: datetime | None = None


class RemoteInviteCreateIn(StrictSchema):
    ttl_seconds: int | None = Field(default=None, ge=300, le=60 * 60 * 24 * 30)
    label: str | None = Field(default=None, max_length=200)


class RemoteContributorJoinIn(StrictSchema):
    token: str = Field(min_length=16, max_length=2000)
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)


class RemoteContributorJoinOut(StrictSchema):
    contributor_id: str
    display_name: str
    email: str
    team_name: str
    assessment_name: str
    topic_label: str
    question_text: str
    evidence_context: str
    # Explicitly never include scores or admin-only evidence


class RemoteTopicOut(StrictSchema):
    team_name: str
    assessment_name: str
    topic_label: str
    question_text: str
    evidence_context: str
    remote_participation_enabled: bool
    invite_valid: bool


class RemoteContributionSubmitOut(StrictSchema):
    id: str
    status: str
    topic: str
    preview: str
    has_attachment: bool
    confirmation_message: str


class RemoteContributionHostOut(StrictSchema):
    id: str
    contributor_name: str
    contributor_email: str | None
    timestamp: datetime
    topic: str
    question_text: str
    body: str
    preview: str
    status: str
    has_attachment: bool
    attachment_filename: str | None = None
    attachment_content_type: str | None = None
    affected_practices: list[str] = Field(default_factory=list)
    interview_turn_id: str | None = None


class RemoteContributionListOut(StrictSchema):
    items: list[RemoteContributionHostOut]
    pending_count: int


class RemoteDispositionIn(StrictSchema):
    action: Literal["include", "defer", "dismiss"]


class RemoteDispositionOut(StrictSchema):
    contribution: RemoteContributionHostOut
    affected_practices: list[str] = Field(default_factory=list)
    notification: str | None = None
    host_question_unchanged: bool = True
