from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.integrations.http import normalize_ado_org_url, normalize_jira_site_url
from app.integrations.jira.types import JIRA_CREDENTIAL_CLASSIC, JIRA_CREDENTIAL_MODES
from app.integrations.permissions import ADO_PERMISSIONS_NOTE, JIRA_PERMISSIONS_NOTE


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JiraCapabilitiesOut(StrictSchema):
    configured: bool = False
    credentials_decryptable: bool = False
    identity_authenticated: bool = False
    project_catalog_accessible: bool = False
    issue_search_accessible: bool | None = None
    last_catalog_refresh_status: str | None = None
    last_catalog_refresh_at: str | None = None
    last_successful_catalog_refresh_at: str | None = None
    last_error_category: str | None = None
    enabled_by_admin: bool = True
    visible_project_count: int | None = None


class AdoCapabilitiesOut(StrictSchema):
    configured: bool = False
    credentials_decryptable: bool = False
    organization_accessible: bool = False
    project_catalog_accessible: bool = False
    repository_catalog_accessible: bool = False
    pipeline_catalog_accessible: bool = False
    last_catalog_refresh_status: str | None = None
    last_catalog_refresh_at: str | None = None
    last_successful_catalog_refresh_at: str | None = None
    last_error_category: str | None = None
    enabled_by_admin: bool = True
    visible_project_count: int | None = None


class ProviderSetupStateOut(StrictSchema):
    availability: str
    capabilities: dict[str, Any]
    catalog_stale: bool = False
    catalog_count: int = 0
    selectable: bool = False


class IntegrationStatusOut(StrictSchema):
    jira_site_url: str | None = None
    jira_service_account_email: str | None = None
    jira_token_configured: bool
    jira_credential_mode: str = JIRA_CREDENTIAL_CLASSIC
    jira_cloud_id: str | None = None
    jira_enabled_by_admin: bool = True
    jira_status: str
    jira_last_validated_at: datetime | None = None
    jira_last_error: str | None = None
    jira_last_error_category: str | None = None
    jira_capabilities: JiraCapabilitiesOut = Field(default_factory=JiraCapabilitiesOut)
    jira_catalog_stale: bool = False
    jira_last_catalog_refresh_status: str | None = None
    jira_last_catalog_refresh_at: datetime | None = None
    jira_last_successful_catalog_refresh_at: datetime | None = None
    ado_org_url: str | None = None
    ado_pat_configured: bool
    ado_enabled_by_admin: bool = True
    ado_status: str
    ado_last_validated_at: datetime | None = None
    ado_last_error: str | None = None
    ado_last_error_category: str | None = None
    ado_capabilities: AdoCapabilitiesOut = Field(default_factory=AdoCapabilitiesOut)
    ado_catalog_stale: bool = False
    ado_last_catalog_refresh_status: str | None = None
    ado_last_catalog_refresh_at: datetime | None = None
    ado_last_successful_catalog_refresh_at: datetime | None = None
    catalog_refreshed_at: datetime | None = None
    jira_permissions_note: str = JIRA_PERMISSIONS_NOTE
    ado_permissions_note: str = ADO_PERMISSIONS_NOTE
    provider_mode: str
    setup_state: dict[str, ProviderSetupStateOut] | None = None
    diagnostics_enabled: bool = False


class JiraCredentialsIn(StrictSchema):
    site_url: str
    service_account_email: str
    api_token: str | None = Field(default=None, min_length=1)
    credential_mode: Literal[
        "classic_account_api_token", "scoped_service_account_token"
    ] = "classic_account_api_token"
    cloud_id: str | None = None
    enabled_by_admin: bool | None = None

    @field_validator("site_url")
    @classmethod
    def _https(cls, value: str) -> str:
        return normalize_jira_site_url(value)

    @field_validator("credential_mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in JIRA_CREDENTIAL_MODES:
            raise ValueError("unsupported credential mode")
        return value


class AdoCredentialsIn(StrictSchema):
    org_url: str
    pat: str | None = Field(default=None, min_length=1)
    enabled_by_admin: bool | None = None

    @field_validator("org_url")
    @classmethod
    def _https(cls, value: str) -> str:
        return normalize_ado_org_url(value)


class ConnectionTestResult(StrictSchema):
    ok: bool
    system: str
    message: str
    tested_at: datetime
    error_category: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)


class CatalogProject(StrictSchema):
    id: str
    key: str | None = None
    name: str
    project_type_key: str | None = None
    style: str | None = None


class CatalogRepo(StrictSchema):
    id: str
    name: str
    default_branch: str


class CatalogPipeline(StrictSchema):
    id: str
    name: str
    runs: int | None = None
    success_rate: str | None = None


class IntegrationDiagnosticsOut(StrictSchema):
    provider: str
    configured_site_or_org: str | None = None
    resolved_api_host: str | None = None
    cloud_id_present: bool | None = None
    credential_mode: str | None = None
    identity_test: str | None = None
    project_catalog_test: str | None = None
    issue_search_test: str | None = None
    repository_test: str | None = None
    pipeline_build_test: str | None = None
    visible_project_count: int | None = None
    last_successful_refresh_at: datetime | None = None
    error_category: str | None = None
    corrective_action: str | None = None
    message: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
