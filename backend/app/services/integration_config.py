from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.errors import AppError
from app.integrations.http import normalize_ado_org_url, normalize_jira_site_url
from app.integrations.jira.types import JIRA_CREDENTIAL_MODES
from app.models import IntegrationConfiguration
from app.models.enums import ConnectionStatus
from app.repositories.integration import IntegrationRepository
from app.services.audit import AuditService


class IntegrationConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = IntegrationRepository(db)
        self.audit = AuditService(db)

    def get(self) -> IntegrationConfiguration:
        return self.repo.get_or_create_singleton()

    def update_jira(
        self,
        *,
        jira_site_url: str | None = None,
        jira_service_account_email: str | None = None,
        jira_api_token: str | None = None,
        jira_credential_mode: str | None = None,
        jira_cloud_id: str | None = None,
        jira_enabled_by_admin: bool | None = None,
    ) -> IntegrationConfiguration:
        record = self.get()
        if jira_site_url is not None:
            record.jira_site_url = normalize_jira_site_url(jira_site_url)
        if jira_service_account_email is not None:
            record.jira_service_account_email = jira_service_account_email.strip()
        if jira_credential_mode is not None:
            mode = jira_credential_mode.strip()
            if mode not in JIRA_CREDENTIAL_MODES:
                raise AppError(
                    code="invalid_jira_credential_mode",
                    message="Unsupported Jira credential mode",
                    status_code=400,
                    details={"error_category": "invalid_configuration"},
                )
            record.jira_credential_mode = mode
        if jira_cloud_id is not None:
            cleaned = jira_cloud_id.strip()
            record.jira_cloud_id = cleaned or None
        if jira_enabled_by_admin is not None:
            record.jira_enabled_by_admin = bool(jira_enabled_by_admin)
        if jira_api_token is not None:
            record.jira_api_token_encrypted = encrypt_secret(jira_api_token)
            record.jira_status = ConnectionStatus.UNKNOWN.value
        self.audit.record(
            event_type="integration.credentials_updated",
            message="Jira integration credentials updated",
            actor_type="admin",
            details={
                "provider": "jira",
                "jira_token_set": bool(jira_api_token),
                "credential_mode": record.jira_credential_mode,
                "cloud_id_set": bool(record.jira_cloud_id),
            },
        )
        self.db.flush()
        return record

    def update_ado(
        self,
        *,
        ado_org_url: str | None = None,
        ado_pat: str | None = None,
        ado_enabled_by_admin: bool | None = None,
    ) -> IntegrationConfiguration:
        record = self.get()
        if ado_org_url is not None:
            record.ado_org_url = normalize_ado_org_url(ado_org_url)
        if ado_enabled_by_admin is not None:
            record.ado_enabled_by_admin = bool(ado_enabled_by_admin)
        if ado_pat is not None:
            record.ado_pat_encrypted = encrypt_secret(ado_pat)
            record.ado_status = ConnectionStatus.UNKNOWN.value
        self.audit.record(
            event_type="integration.credentials_updated",
            message="Azure DevOps integration credentials updated",
            actor_type="admin",
            details={"provider": "azure_devops", "ado_pat_set": bool(ado_pat)},
        )
        self.db.flush()
        return record

    def update_credentials(
        self,
        *,
        jira_site_url: str | None = None,
        jira_service_account_email: str | None = None,
        jira_api_token: str | None = None,
        ado_org_url: str | None = None,
        ado_pat: str | None = None,
        jira_credential_mode: str | None = None,
        jira_cloud_id: str | None = None,
        jira_enabled_by_admin: bool | None = None,
        ado_enabled_by_admin: bool | None = None,
    ) -> IntegrationConfiguration:
        # Backward-compatible combined updater used by older callers/tests.
        if any(
            v is not None
            for v in (
                jira_site_url,
                jira_service_account_email,
                jira_api_token,
                jira_credential_mode,
                jira_cloud_id,
                jira_enabled_by_admin,
            )
        ):
            self.update_jira(
                jira_site_url=jira_site_url,
                jira_service_account_email=jira_service_account_email,
                jira_api_token=jira_api_token,
                jira_credential_mode=jira_credential_mode,
                jira_cloud_id=jira_cloud_id,
                jira_enabled_by_admin=jira_enabled_by_admin,
            )
        if any(v is not None for v in (ado_org_url, ado_pat, ado_enabled_by_admin)):
            self.update_ado(
                ado_org_url=ado_org_url,
                ado_pat=ado_pat,
                ado_enabled_by_admin=ado_enabled_by_admin,
            )
        return self.get()

    def reveal_jira_token(self, record: IntegrationConfiguration) -> str:
        return decrypt_secret(record.jira_api_token_encrypted or "")

    def reveal_ado_pat(self, record: IntegrationConfiguration) -> str:
        return decrypt_secret(record.ado_pat_encrypted or "")

    def mark_validated(
        self,
        *,
        system: str,
        ok: bool,
        error: str | None = None,
        error_category: str | None = None,
    ) -> IntegrationConfiguration:
        record = self.get()
        now = datetime.now(UTC)
        if system == "jira":
            record.jira_status = (
                ConnectionStatus.CONNECTED.value if ok else ConnectionStatus.FAILED.value
            )
            record.jira_last_validated_at = now
            record.jira_last_error = None if ok else error
            record.jira_last_error_category = None if ok else error_category
        elif system == "ado":
            record.ado_status = (
                ConnectionStatus.CONNECTED.value if ok else ConnectionStatus.FAILED.value
            )
            record.ado_last_validated_at = now
            record.ado_last_error = None if ok else error
            record.ado_last_error_category = None if ok else error_category
        self.db.flush()
        return record
