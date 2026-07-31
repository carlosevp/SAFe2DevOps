from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.schemas.remote import (
    RemoteContributionHostOut,
    RemoteContributionListOut,
    RemoteContributionSubmitOut,
    RemoteContributorJoinIn,
    RemoteContributorJoinOut,
    RemoteDispositionIn,
    RemoteDispositionOut,
    RemoteInviteCreateIn,
    RemoteInviteOut,
    RemoteSettingsOut,
    RemoteSettingsUpdate,
    RemoteTopicOut,
)
from app.services.remote import RemoteParticipationService

router = APIRouter(tags=["remote"])


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _base_url(request: Request) -> str:
    # Prefer configured public URL; fall back to request origin for local/dev.
    from app.core.config import get_settings

    settings = get_settings()
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("/assessments/{assessment_id}/remote", response_model=RemoteSettingsOut)
def get_remote_settings(
    assessment_id: str,
    request: Request,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteSettingsOut:
    return RemoteParticipationService(db).get_settings_out(
        assessment_id, base_url=_base_url(request)
    )


@router.put("/assessments/{assessment_id}/remote", response_model=RemoteSettingsOut)
def update_remote_settings(
    assessment_id: str,
    body: RemoteSettingsUpdate,
    request: Request,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteSettingsOut:
    service = RemoteParticipationService(db)
    service.set_enabled(
        assessment_id, body.remote_participation_enabled, actor=admin.get("subject", "admin")
    )
    db.commit()
    return service.get_settings_out(assessment_id, base_url=_base_url(request))


@router.post("/assessments/{assessment_id}/remote/invites", response_model=RemoteInviteOut)
def create_remote_invite(
    assessment_id: str,
    body: RemoteInviteCreateIn,
    request: Request,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteInviteOut:
    invite = RemoteParticipationService(db).create_invite(
        assessment_id,
        base_url=_base_url(request),
        actor=admin.get("subject", "admin"),
        ttl_seconds=body.ttl_seconds,
        label=body.label,
    )
    db.commit()
    return invite


@router.post(
    "/assessments/{assessment_id}/remote/invites/{jti}/revoke", response_model=RemoteInviteOut
)
def revoke_remote_invite(
    assessment_id: str,
    jti: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteInviteOut:
    out = RemoteParticipationService(db).revoke_invite(
        assessment_id, jti, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.get(
    "/assessments/{assessment_id}/remote/contributions", response_model=RemoteContributionListOut
)
def list_remote_contributions(
    assessment_id: str,
    status: str | None = None,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteContributionListOut:
    return RemoteParticipationService(db).list_contributions(assessment_id, status=status)


@router.get(
    "/assessments/{assessment_id}/remote/contributions/{contribution_id}",
    response_model=RemoteContributionHostOut,
)
def get_remote_contribution(
    assessment_id: str,
    contribution_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteContributionHostOut:
    return RemoteParticipationService(db).get_contribution(assessment_id, contribution_id)


@router.post(
    "/assessments/{assessment_id}/remote/contributions/{contribution_id}/disposition",
    response_model=RemoteDispositionOut,
)
def dispose_remote_contribution(
    assessment_id: str,
    contribution_id: str,
    body: RemoteDispositionIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> RemoteDispositionOut:
    out = RemoteParticipationService(db).dispose(
        assessment_id,
        contribution_id,
        action=body.action,
        actor=admin.get("subject", "admin"),
    )
    db.commit()
    return out


@router.get("/remote/topic", response_model=RemoteTopicOut)
def remote_topic(
    token: str,
    request: Request,
    db: Session = Depends(get_db_session),
) -> RemoteTopicOut:
    return RemoteParticipationService(db).get_topic(token, client_key=_client_key(request))


@router.post("/remote/join", response_model=RemoteContributorJoinOut)
def remote_join(
    body: RemoteContributorJoinIn,
    request: Request,
    db: Session = Depends(get_db_session),
) -> RemoteContributorJoinOut:
    out = RemoteParticipationService(db).join(
        token=body.token,
        display_name=body.display_name,
        email=body.email,
        client_key=_client_key(request),
    )
    db.commit()
    return out


@router.post("/remote/contributions", response_model=RemoteContributionSubmitOut)
async def remote_submit_contribution(
    request: Request,
    token: str = Form(...),
    contributor_id: str = Form(...),
    body: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    db: Session = Depends(get_db_session),
) -> RemoteContributionSubmitOut:
    attachment_bytes: bytes | None = None
    attachment_name: str | None = None
    attachment_type: str | None = None
    if attachment is not None and attachment.filename:
        attachment_bytes = await attachment.read(2 * 1024 * 1024 + 1)
        attachment_name = attachment.filename
        attachment_type = attachment.content_type
    out = RemoteParticipationService(db).submit_contribution(
        token=token,
        contributor_id=contributor_id,
        body=body,
        client_key=_client_key(request),
        attachment_name=attachment_name,
        attachment_content_type=attachment_type,
        attachment_bytes=attachment_bytes,
    )
    db.commit()
    return out
