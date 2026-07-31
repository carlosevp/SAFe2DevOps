from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.errors import AppError
from app.core.rate_limit import rate_limiter
from app.core.security import issue_assessment_access_token, verify_assessment_access_token
from app.integrations.http import sanitize_remote_text
from app.models import Assessment, RemoteContribution, RemoteContributor, RemoteInvite
from app.models.access_token import AccessTokenRevocation
from app.models.ai_settings import InterviewSession
from app.models.enums import RemoteContributionStatus
from app.schemas.remote import (
    RemoteContributionHostOut,
    RemoteContributionListOut,
    RemoteContributionSubmitOut,
    RemoteContributorJoinOut,
    RemoteDispositionOut,
    RemoteInviteOut,
    RemoteSettingsOut,
    RemoteTopicOut,
)
from app.services.audit import AuditService
from app.services.interview import InterviewService
from app.services.storage import StorageService
from app.services.tokens import AssessmentAccessTokenService

SAFE_ATTACHMENT_TYPES = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "text/plain": {".txt", ".md", ".text"},
    "text/markdown": {".md", ".markdown"},
}
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class RemoteParticipationService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.audit = AuditService(db)
        self.tokens = AssessmentAccessTokenService(self.settings)
        self.storage = StorageService(self.settings)
        self.interview = InterviewService(db)

    def get_settings_out(self, assessment_id: str, *, base_url: str) -> RemoteSettingsOut:
        assessment = self._require_assessment(assessment_id)
        invite = self._active_invite(assessment_id)
        pending = self.db.scalar(
            select(func.count())
            .select_from(RemoteContribution)
            .where(
                RemoteContribution.assessment_id == assessment_id,
                RemoteContribution.status == RemoteContributionStatus.PENDING.value,
            )
        )
        return RemoteSettingsOut(
            assessment_id=assessment_id,
            remote_participation_enabled=bool(assessment.remote_participation_enabled),
            active_invite=self._invite_out(invite, base_url) if invite else None,
            pending_count=int(pending or 0),
        )

    def set_enabled(self, assessment_id: str, enabled: bool, *, actor: str) -> RemoteSettingsOut:
        assessment = self._require_assessment(assessment_id)
        assessment.remote_participation_enabled = bool(enabled)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="remote.participation_toggled",
            message="Remote participation enabled" if enabled else "Remote participation disabled",
            actor_type="admin",
            actor_subject=actor,
            details={"enabled": enabled},
        )
        self.db.flush()
        return self.get_settings_out(assessment_id, base_url="")

    def create_invite(
        self,
        assessment_id: str,
        *,
        base_url: str,
        actor: str,
        ttl_seconds: int | None = None,
        label: str | None = None,
    ) -> RemoteInviteOut:
        assessment = self._require_assessment(assessment_id)
        if not assessment.remote_participation_enabled:
            raise AppError(
                code="remote_participation_disabled",
                message="Enable remote participation before creating an invite",
                status_code=409,
            )
        # Revoke any previous active invite so only one link is live.
        for prior in self.db.scalars(
            select(RemoteInvite).where(
                RemoteInvite.assessment_id == assessment_id,
                RemoteInvite.revoked_at.is_(None),
            )
        ):
            prior.revoked_at = datetime.now(UTC)
            self.tokens.revoke(
                self.db, jti=prior.jti, assessment_id=assessment_id, reason="replaced"
            )

        ttl = ttl_seconds or self.settings.remote_invite_ttl_seconds
        token, jti, expires_at = issue_assessment_access_token(
            self.settings,
            assessment_id=assessment_id,
            role="remote",
            ttl_seconds=ttl,
        )
        invite = RemoteInvite(
            assessment_id=assessment_id,
            jti=jti,
            token_ciphertext=encrypt_secret(token, self.settings),
            expires_at=expires_at,
            created_by=actor,
            label=sanitize_remote_text(label or "", max_len=200) or None,
        )
        self.db.add(invite)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="remote.invite_created",
            message="Remote invite link created",
            actor_type="admin",
            actor_subject=actor,
            details={"jti": jti, "expires_at": expires_at.isoformat()},
        )
        self.db.flush()
        return self._invite_out(invite, base_url)

    def revoke_invite(self, assessment_id: str, jti: str, *, actor: str) -> RemoteInviteOut:
        invite = self.db.scalar(
            select(RemoteInvite).where(
                RemoteInvite.assessment_id == assessment_id, RemoteInvite.jti == jti
            )
        )
        if invite is None:
            raise AppError(code="invite_not_found", message="Invite not found", status_code=404)
        if invite.revoked_at is None:
            invite.revoked_at = datetime.now(UTC)
            self.tokens.revoke(self.db, jti=jti, assessment_id=assessment_id, reason="host_revoked")
            self.audit.record(
                assessment_id=assessment_id,
                event_type="remote.invite_revoked",
                message="Remote invite revoked",
                actor_type="admin",
                actor_subject=actor,
                details={"jti": jti},
            )
            self.db.flush()
        return RemoteInviteOut(
            jti=invite.jti,
            invite_url="",
            expires_at=invite.expires_at,
            revoked=True,
            created_at=invite.created_at,
        )

    def get_topic(self, token: str, *, client_key: str) -> RemoteTopicOut:
        rate_limiter.check(f"remote-topic:{client_key}", limit=60, window_seconds=60)
        payload = self._verify_remote_token(token)
        assessment = self._require_assessment(payload["assessment_id"])
        if not assessment.remote_participation_enabled:
            raise AppError(
                code="remote_participation_disabled",
                message="Remote participation is disabled",
                status_code=403,
            )
        topic = self._topic_for_assessment(assessment)
        return RemoteTopicOut(
            team_name=assessment.team_name,
            assessment_name=assessment.product_service_name,
            topic_label=topic["topic_label"],
            question_text=topic["question_text"],
            evidence_context=topic["evidence_context"],
            remote_participation_enabled=True,
            invite_valid=True,
        )

    def join(
        self, *, token: str, display_name: str, email: str, client_key: str
    ) -> RemoteContributorJoinOut:
        rate_limiter.check(f"remote-join:{client_key}", limit=10, window_seconds=60)
        payload = self._verify_remote_token(token)
        assessment_id = payload["assessment_id"]
        assessment = self._require_assessment(assessment_id)
        if not assessment.remote_participation_enabled:
            raise AppError(
                code="remote_participation_disabled",
                message="Remote participation is disabled",
                status_code=403,
            )

        name = sanitize_remote_text(display_name, max_len=200).strip()
        clean_email = sanitize_remote_text(email, max_len=320).strip().lower()
        if not name or "@" not in clean_email:
            raise AppError(
                code="invalid_contributor",
                message="Name and valid email are required",
                status_code=400,
            )

        existing = self.db.scalar(
            select(RemoteContributor).where(
                RemoteContributor.assessment_id == assessment_id,
                RemoteContributor.email == clean_email,
            )
        )
        if existing is None:
            existing = RemoteContributor(
                assessment_id=assessment_id,
                display_name=name,
                email=clean_email,
                invite_token_jti=payload["jti"],
            )
            self.db.add(existing)
        else:
            existing.display_name = name
            existing.invite_token_jti = payload["jti"]
        self.audit.record(
            assessment_id=assessment_id,
            event_type="remote.contributor_joined",
            message="Remote contributor joined",
            actor_type="remote",
            actor_subject=clean_email,
            details={"contributor_id": existing.id if existing.id else None},
        )
        self.db.flush()
        topic = self._topic_for_assessment(assessment)
        return RemoteContributorJoinOut(
            contributor_id=existing.id,
            display_name=existing.display_name,
            email=clean_email,
            team_name=assessment.team_name,
            assessment_name=assessment.product_service_name,
            topic_label=topic["topic_label"],
            question_text=topic["question_text"],
            evidence_context=topic["evidence_context"],
        )

    def submit_contribution(
        self,
        *,
        token: str,
        contributor_id: str,
        body: str,
        client_key: str,
        attachment_name: str | None = None,
        attachment_content_type: str | None = None,
        attachment_bytes: bytes | None = None,
    ) -> RemoteContributionSubmitOut:
        rate_limiter.check(f"remote-submit:{client_key}", limit=20, window_seconds=60)
        payload = self._verify_remote_token(token)
        assessment_id = payload["assessment_id"]
        assessment = self._require_assessment(assessment_id)
        if not assessment.remote_participation_enabled:
            raise AppError(
                code="remote_participation_disabled",
                message="Remote participation is disabled",
                status_code=403,
            )

        contributor = self.db.get(RemoteContributor, contributor_id)
        if contributor is None or contributor.assessment_id != assessment_id:
            raise AppError(
                code="contributor_not_found",
                message="Contributor not found for this invite",
                status_code=404,
            )

        clean_body = sanitize_remote_text(body, max_len=20000).strip()
        if not clean_body:
            raise AppError(
                code="empty_contribution", message="Contribution text is required", status_code=400
            )

        topic = self._topic_for_assessment(assessment)
        contribution = RemoteContribution(
            assessment_id=assessment_id,
            contributor_id=contributor.id,
            topic=topic["topic_label"],
            question_text=topic["question_text"],
            evidence_context=topic["evidence_context"],
            body=clean_body,
            status=RemoteContributionStatus.PENDING.value,
            content_trust="untrusted",
        )
        self.db.add(contribution)
        self.db.flush()

        if attachment_bytes is not None:
            self._store_attachment(
                contribution,
                filename=attachment_name or "attachment.bin",
                content_type=attachment_content_type or "application/octet-stream",
                data=attachment_bytes,
            )

        self.audit.record(
            assessment_id=assessment_id,
            event_type="remote.contribution_submitted",
            message="Remote contribution submitted",
            actor_type="remote",
            actor_subject=contributor.email or contributor.display_name,
            details={
                "contribution_id": contribution.id,
                "has_attachment": bool(contribution.attachment_storage_path),
                "topic": contribution.topic,
            },
        )
        self.db.flush()
        preview = clean_body[:160] + ("…" if len(clean_body) > 160 else "")
        return RemoteContributionSubmitOut(
            id=contribution.id,
            status=contribution.status,
            topic=contribution.topic,
            preview=preview,
            has_attachment=bool(contribution.attachment_storage_path),
            confirmation_message=(
                "Your contribution has been added for the host to review. "
                "It will be included in the assessment at their discretion."
            ),
        )

    def list_contributions(
        self,
        assessment_id: str,
        *,
        status: str | None = None,
    ) -> RemoteContributionListOut:
        self._require_assessment(assessment_id)
        stmt = (
            select(RemoteContribution)
            .options(selectinload(RemoteContribution.contributor))
            .where(RemoteContribution.assessment_id == assessment_id)
            .order_by(RemoteContribution.created_at.desc())
        )
        if status:
            stmt = stmt.where(RemoteContribution.status == status)
        rows = list(self.db.scalars(stmt))
        pending = sum(1 for row in rows if row.status == RemoteContributionStatus.PENDING.value)
        if status is None:
            pending = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(RemoteContribution)
                    .where(
                        RemoteContribution.assessment_id == assessment_id,
                        RemoteContribution.status == RemoteContributionStatus.PENDING.value,
                    )
                )
                or 0
            )
        return RemoteContributionListOut(
            items=[self._contribution_out(row) for row in rows],
            pending_count=pending
            if status != RemoteContributionStatus.PENDING.value
            else len(rows),
        )

    def get_contribution(
        self, assessment_id: str, contribution_id: str
    ) -> RemoteContributionHostOut:
        row = self._require_contribution(assessment_id, contribution_id)
        return self._contribution_out(row)

    def dispose(
        self,
        assessment_id: str,
        contribution_id: str,
        *,
        action: str,
        actor: str,
    ) -> RemoteDispositionOut:
        row = self._require_contribution(assessment_id, contribution_id)
        if row.status != RemoteContributionStatus.PENDING.value and action == "include":
            raise AppError(
                code="already_disposed",
                message="Contribution is no longer pending",
                status_code=409,
            )

        affected: list[str] = []
        notification: str | None = None
        host_unchanged = True

        if action == "include":
            if row.status == RemoteContributionStatus.INCLUDED.value and row.interview_turn_id:
                affected = json.loads(row.affected_practices_json or "[]")
            else:
                frozen = self.interview.get_session(assessment_id)
                result = self.interview.ingest_remote_contribution(
                    assessment_id,
                    answer_text=row.body,
                    question_text=row.question_text,
                    idempotency_key=f"remote:{contribution_id}",
                    actor=actor,
                )
                affected = list(result.get("affected_practices") or [])
                row.interview_turn_id = result["turn_id"]
                row.affected_practices_json = json.dumps(affected)
                row.status = RemoteContributionStatus.INCLUDED.value
                row.host_notified = True
                host_unchanged = bool(result.get("host_question_unchanged", True))
                # Confirm host screen still matches pre-include snapshot.
                after = self.interview.get_session(assessment_id)
                if after.current_question != frozen.current_question:
                    host_unchanged = False
                notification = f"Included contribution from {row.contributor.display_name}. " + (
                    f"Practices affected: {', '.join(affected)}."
                    if affected
                    else "No practice coverage changes were produced."
                )
        elif action == "defer":
            row.status = RemoteContributionStatus.DEFERRED.value
            notification = f"Deferred contribution from {row.contributor.display_name}."
        elif action == "dismiss":
            row.status = RemoteContributionStatus.DISMISSED.value
            notification = f"Dismissed contribution from {row.contributor.display_name}."
        else:
            raise AppError(
                code="invalid_disposition", message="Unknown disposition action", status_code=400
            )

        row.disposition_by = actor
        row.disposition_at = datetime.now(UTC)
        self.audit.record(
            assessment_id=assessment_id,
            event_type="remote.contribution_disposition",
            message=f"Remote contribution {action}",
            actor_type="admin",
            actor_subject=actor,
            details={
                "contribution_id": contribution_id,
                "action": action,
                "status": row.status,
                "affected_practices": affected,
            },
        )
        self.db.flush()
        return RemoteDispositionOut(
            contribution=self._contribution_out(row),
            affected_practices=affected,
            notification=notification,
            host_question_unchanged=host_unchanged,
        )

    def _verify_remote_token(self, token: str) -> dict[str, str]:
        try:
            payload = verify_assessment_access_token(self.settings, token)
        except ValueError as exc:
            code = str(exc)
            raise AppError(code=code, message="Invite link is not valid", status_code=401) from exc
        if payload.get("role") != "remote":
            raise AppError(
                code="token_invalid",
                message="Invite link is not valid for remote access",
                status_code=401,
            )
        jti = str(payload["jti"])
        assessment_id = str(payload.get("assessment_id", ""))
        revoked = self.db.scalar(
            select(AccessTokenRevocation).where(AccessTokenRevocation.jti == jti)
        )
        if revoked is not None:
            raise AppError(
                code="token_revoked", message="Invite link has been revoked", status_code=401
            )
        invite = self.db.scalar(select(RemoteInvite).where(RemoteInvite.jti == jti))
        if invite is None or invite.assessment_id != assessment_id:
            raise AppError(
                code="invite_not_found", message="Invite link is not recognized", status_code=401
            )
        if invite.revoked_at is not None:
            raise AppError(
                code="token_revoked", message="Invite link has been revoked", status_code=401
            )
        expires = invite.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            raise AppError(code="token_expired", message="Invite link has expired", status_code=401)
        return {"jti": jti, "assessment_id": assessment_id, "role": "remote"}

    def _topic_for_assessment(self, assessment: Assessment) -> dict[str, str]:
        session = self.db.scalar(
            select(InterviewSession).where(InterviewSession.assessment_id == assessment.id)
        )
        if session and session.current_question:
            return {
                "topic_label": session.topic_label or "Current topic",
                "question_text": session.current_question,
                # Only expose the workshop-safe evidence context — never admin review scores.
                "evidence_context": session.evidence_context or "",
            }
        # Async contribution when interview not started: unresolved generic topic.
        return {
            "topic_label": "Team delivery practices",
            "question_text": (
                f"Share your perspective on how {assessment.team_name} delivers "
                f"{assessment.product_service_name} from idea to production."
            ),
            "evidence_context": "The host will review your contribution alongside workshop discussion.",
        }

    def _store_attachment(
        self,
        contribution: RemoteContribution,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> None:
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise AppError(
                code="attachment_too_large",
                message="Attachment exceeds 2 MB limit",
                status_code=400,
            )
        if len(data) == 0:
            raise AppError(code="attachment_empty", message="Attachment is empty", status_code=400)

        content_type = (content_type or "").split(";")[0].strip().lower()
        allowed_exts = SAFE_ATTACHMENT_TYPES.get(content_type)
        if not allowed_exts:
            raise AppError(
                code="attachment_type_rejected",
                message="Attachment type not allowed. Use PDF, PNG, JPEG, TXT, or Markdown.",
                status_code=400,
            )

        raw_name = Path(filename).name
        safe = SAFE_NAME_RE.sub("_", raw_name).strip("._") or "attachment"
        ext = Path(safe).suffix.lower()
        if ext not in allowed_exts:
            # Normalize extension to a safe default for the content type.
            ext = sorted(allowed_exts)[0]
            safe = f"{Path(safe).stem or 'attachment'}{ext}"

        # Reject path tricks and polyglot-ish names.
        if ".." in safe or "/" in safe or "\\" in safe:
            raise AppError(
                code="attachment_name_rejected", message="Unsafe attachment name", status_code=400
            )

        # Basic content sniffing for common types.
        if content_type == "application/pdf" and not data.startswith(b"%PDF"):
            raise AppError(
                code="attachment_content_mismatch",
                message="PDF content does not match type",
                status_code=400,
            )
        if content_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AppError(
                code="attachment_content_mismatch",
                message="PNG content does not match type",
                status_code=400,
            )
        if content_type == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
            raise AppError(
                code="attachment_content_mismatch",
                message="JPEG content does not match type",
                status_code=400,
            )

        paths = self.storage.ensure_directories()
        directory = paths.uploads / "remote" / contribution.assessment_id / contribution.id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe
        target.write_bytes(data)
        contribution.attachment_filename = safe
        contribution.attachment_content_type = content_type
        contribution.attachment_size = len(data)
        contribution.attachment_storage_path = str(target.relative_to(paths.data_dir))

    def _active_invite(self, assessment_id: str) -> RemoteInvite | None:
        now = datetime.now(UTC)
        invites = list(
            self.db.scalars(
                select(RemoteInvite)
                .where(
                    RemoteInvite.assessment_id == assessment_id, RemoteInvite.revoked_at.is_(None)
                )
                .order_by(RemoteInvite.created_at.desc())
            )
        )
        for invite in invites:
            expires = (
                invite.expires_at
                if invite.expires_at.tzinfo
                else invite.expires_at.replace(tzinfo=UTC)
            )
            if expires >= now:
                return invite
        return None

    def _invite_out(self, invite: RemoteInvite, base_url: str) -> RemoteInviteOut:
        token = (
            decrypt_secret(invite.token_ciphertext, self.settings)
            if invite.token_ciphertext
            else ""
        )
        root = (base_url or self.settings.public_base_url or "").rstrip("/")
        url = (
            f"{root}/?invite={token}" if token and root else (f"/?invite={token}" if token else "")
        )
        return RemoteInviteOut(
            jti=invite.jti,
            invite_url=url,
            expires_at=invite.expires_at,
            revoked=invite.revoked_at is not None,
            created_at=invite.created_at,
        )

    def _contribution_out(self, row: RemoteContribution) -> RemoteContributionHostOut:
        body = row.body or ""
        return RemoteContributionHostOut(
            id=row.id,
            contributor_name=row.contributor.display_name if row.contributor else "Unknown",
            contributor_email=row.contributor.email if row.contributor else None,
            timestamp=row.created_at,
            topic=row.topic,
            question_text=row.question_text,
            body=body,
            preview=body[:160] + ("…" if len(body) > 160 else ""),
            status=row.status,
            has_attachment=bool(row.attachment_storage_path),
            attachment_filename=row.attachment_filename,
            attachment_content_type=row.attachment_content_type,
            affected_practices=json.loads(row.affected_practices_json or "[]"),
            interview_turn_id=row.interview_turn_id,
        )

    def _require_assessment(self, assessment_id: str) -> Assessment:
        assessment = self.db.get(Assessment, assessment_id)
        if assessment is None:
            raise AppError(
                code="assessment_not_found", message="Assessment not found", status_code=404
            )
        return assessment

    def _require_contribution(self, assessment_id: str, contribution_id: str) -> RemoteContribution:
        row = self.db.scalar(
            select(RemoteContribution)
            .options(selectinload(RemoteContribution.contributor))
            .where(
                RemoteContribution.id == contribution_id,
                RemoteContribution.assessment_id == assessment_id,
            )
        )
        if row is None:
            raise AppError(
                code="contribution_not_found", message="Contribution not found", status_code=404
            )
        return row
