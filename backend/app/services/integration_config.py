from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.encryption import decrypt_secret, encrypt_secret
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

    def update_credentials(
        self,
        *,
        jira_site_url: str | None = None,
        jira_service_account_email: str | None = None,
        jira_api_token: str | None = None,
        ado_org_url: str | None = None,
        ado_pat: str | None = None,
    ) -> IntegrationConfiguration:
        record = self.get()
        if jira_site_url is not None:
            record.jira_site_url = jira_site_url
        if jira_service_account_email is not None:
            record.jira_service_account_email = jira_service_account_email
        if jira_api_token is not None:
            record.jira_api_token_encrypted = encrypt_secret(jira_api_token)
            record.jira_status = ConnectionStatus.UNKNOWN.value
        if ado_org_url is not None:
            record.ado_org_url = ado_org_url
        if ado_pat is not None:
            record.ado_pat_encrypted = encrypt_secret(ado_pat)
            record.ado_status = ConnectionStatus.UNKNOWN.value
        self.audit.record(
            event_type="integration.credentials_updated",
            message="Integration credentials updated",
            actor_type="admin",
            details={"jira_token_set": bool(jira_api_token), "ado_pat_set": bool(ado_pat)},
        )
        self.db.flush()
        return record

    def reveal_jira_token(self, record: IntegrationConfiguration) -> str:
        return decrypt_secret(record.jira_api_token_encrypted or "")

    def reveal_ado_pat(self, record: IntegrationConfiguration) -> str:
        return decrypt_secret(record.ado_pat_encrypted or "")

    def mark_validated(self, *, system: str, ok: bool, error: str | None = None) -> IntegrationConfiguration:
        record = self.get()
        now = datetime.now(UTC)
        if system == "jira":
            record.jira_status = ConnectionStatus.CONNECTED.value if ok else ConnectionStatus.FAILED.value
            record.jira_last_validated_at = now
            record.jira_last_error = None if ok else error
        elif system == "ado":
            record.ado_status = ConnectionStatus.CONNECTED.value if ok else ConnectionStatus.FAILED.value
            record.ado_last_validated_at = now
            record.ado_last_error = None if ok else error
        self.db.flush()
        return record
