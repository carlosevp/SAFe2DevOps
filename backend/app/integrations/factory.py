from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.integrations.ado.client import AdoProvider, LiveAdoProvider
from app.integrations.ado.mock import MockAdoProvider
from app.integrations.diagnostics import emit_integration_event
from app.integrations.jira.client import JiraProvider, LiveJiraProvider
from app.integrations.jira.mock import MockJiraProvider
from app.integrations.jira.types import JIRA_CREDENTIAL_CLASSIC
from app.services.integration_config import IntegrationConfigService


@dataclass(slots=True)
class IntegrationProviders:
    jira: JiraProvider | None
    ado: AdoProvider | None
    mode: str


def get_jira_provider(db: Session, settings: Settings | None = None) -> JiraProvider:
    settings = settings or get_settings()
    if (settings.integration_provider or "mock").lower() == "mock":
        return MockJiraProvider()

    cfg = IntegrationConfigService(db)
    record = cfg.get()
    emit_integration_event(
        "integration.configuration.loaded",
        provider="jira",
        integration_config_id=record.id,
        operation="get_jira_provider",
    )
    if not record.jira_site_url or not record.jira_service_account_email:
        raise AppError(
            code="jira_not_configured",
            message="Jira integration is not configured",
            status_code=400,
            details={"error_category": "not_configured"},
        )
    if not record.jira_api_token_encrypted:
        raise AppError(
            code="jira_not_configured",
            message="Jira API token is not configured",
            status_code=400,
            details={"error_category": "not_configured"},
        )
    emit_integration_event(
        "integration.credential.decrypt.started",
        provider="jira",
        integration_config_id=record.id,
        operation="reveal_jira_token",
    )
    try:
        token = cfg.reveal_jira_token(record)
        emit_integration_event(
            "integration.credential.decrypt.succeeded",
            provider="jira",
            integration_config_id=record.id,
            operation="reveal_jira_token",
        )
    except AppError as exc:
        emit_integration_event(
            "integration.credential.decrypt.failed",
            provider="jira",
            integration_config_id=record.id,
            operation="reveal_jira_token",
            error_category="secret_decrypt_failed",
            sanitized_external_error=exc.message,
        )
        raise
    return LiveJiraProvider(
        site_url=record.jira_site_url,
        email=record.jira_service_account_email,
        api_token=token,
        credential_mode=getattr(record, "jira_credential_mode", None) or JIRA_CREDENTIAL_CLASSIC,
        cloud_id=getattr(record, "jira_cloud_id", None),
        integration_config_id=record.id,
    )


def get_ado_provider(db: Session, settings: Settings | None = None) -> AdoProvider:
    settings = settings or get_settings()
    if (settings.integration_provider or "mock").lower() == "mock":
        return MockAdoProvider()

    cfg = IntegrationConfigService(db)
    record = cfg.get()
    emit_integration_event(
        "integration.configuration.loaded",
        provider="azure_devops",
        integration_config_id=record.id,
        operation="get_ado_provider",
    )
    if not record.ado_org_url or not record.ado_pat_encrypted:
        raise AppError(
            code="ado_not_configured",
            message="Azure DevOps integration is not configured",
            status_code=400,
            details={"error_category": "not_configured"},
        )
    emit_integration_event(
        "integration.credential.decrypt.started",
        provider="azure_devops",
        integration_config_id=record.id,
        operation="reveal_ado_pat",
    )
    try:
        pat = cfg.reveal_ado_pat(record)
        emit_integration_event(
            "integration.credential.decrypt.succeeded",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="reveal_ado_pat",
        )
    except AppError as exc:
        emit_integration_event(
            "integration.credential.decrypt.failed",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="reveal_ado_pat",
            error_category="secret_decrypt_failed",
            sanitized_external_error=exc.message,
        )
        raise
    return LiveAdoProvider(
        org_url=record.ado_org_url, pat=pat, integration_config_id=record.id
    )


def get_integration_providers(
    db: Session,
    settings: Settings | None = None,
    *,
    require_jira: bool = True,
    require_ado: bool = True,
) -> IntegrationProviders:
    """Return providers independently. Only required sides are constructed."""
    settings = settings or get_settings()
    mode = (settings.integration_provider or "mock").lower()
    if mode == "mock":
        return IntegrationProviders(jira=MockJiraProvider(), ado=MockAdoProvider(), mode="mock")

    jira: JiraProvider | None = None
    ado: AdoProvider | None = None
    if require_jira:
        jira = get_jira_provider(db, settings)
    if require_ado:
        ado = get_ado_provider(db, settings)
    return IntegrationProviders(jira=jira, ado=ado, mode="live")
