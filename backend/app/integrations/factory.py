from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.integrations.ado.client import AdoProvider, LiveAdoProvider
from app.integrations.ado.mock import MockAdoProvider
from app.integrations.http import validate_https_url
from app.integrations.jira.client import JiraProvider, LiveJiraProvider
from app.integrations.jira.mock import MockJiraProvider
from app.services.integration_config import IntegrationConfigService


@dataclass(slots=True)
class IntegrationProviders:
    jira: JiraProvider
    ado: AdoProvider
    mode: str


def get_integration_providers(
    db: Session, settings: Settings | None = None
) -> IntegrationProviders:
    settings = settings or get_settings()
    mode = (settings.integration_provider or "mock").lower()
    if mode == "mock":
        return IntegrationProviders(jira=MockJiraProvider(), ado=MockAdoProvider(), mode="mock")

    cfg = IntegrationConfigService(db)
    record = cfg.get()
    if (
        not record.jira_site_url
        or not record.jira_service_account_email
        or not record.jira_api_token_encrypted
    ):
        raise AppError(
            code="jira_not_configured",
            message="Jira integration is not configured",
            status_code=400,
        )
    if not record.ado_org_url or not record.ado_pat_encrypted:
        raise AppError(
            code="ado_not_configured",
            message="Azure DevOps integration is not configured",
            status_code=400,
        )

    validate_https_url(record.jira_site_url, label="Jira site URL")
    validate_https_url(record.ado_org_url, label="Azure DevOps organization URL")

    jira = LiveJiraProvider(
        site_url=record.jira_site_url,
        email=record.jira_service_account_email,
        api_token=cfg.reveal_jira_token(record),
    )
    ado = LiveAdoProvider(org_url=record.ado_org_url, pat=cfg.reveal_ado_pat(record))
    return IntegrationProviders(jira=jira, ado=ado, mode="live")
