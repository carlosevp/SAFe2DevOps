from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.integrations.http import validate_https_url
from app.integrations.permissions import ADO_PERMISSIONS_NOTE, JIRA_PERMISSIONS_NOTE


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntegrationStatusOut(StrictSchema):
    jira_site_url: str | None = None
    jira_service_account_email: str | None = None
    jira_token_configured: bool
    jira_status: str
    jira_last_validated_at: datetime | None = None
    jira_last_error: str | None = None
    ado_org_url: str | None = None
    ado_pat_configured: bool
    ado_status: str
    ado_last_validated_at: datetime | None = None
    ado_last_error: str | None = None
    catalog_refreshed_at: datetime | None = None
    jira_permissions_note: str = JIRA_PERMISSIONS_NOTE
    ado_permissions_note: str = ADO_PERMISSIONS_NOTE
    provider_mode: str


class JiraCredentialsIn(StrictSchema):
    site_url: str
    service_account_email: str
    api_token: str | None = Field(default=None, min_length=1)

    @field_validator("site_url")
    @classmethod
    def _https(cls, value: str) -> str:
        return validate_https_url(value, label="Jira site URL")


class AdoCredentialsIn(StrictSchema):
    org_url: str
    pat: str | None = Field(default=None, min_length=1)

    @field_validator("org_url")
    @classmethod
    def _https(cls, value: str) -> str:
        return validate_https_url(value, label="Azure DevOps organization URL")


class ConnectionTestResult(StrictSchema):
    ok: bool
    system: str
    message: str
    tested_at: datetime


class CatalogProject(StrictSchema):
    id: str
    key: str | None = None
    name: str


class CatalogRepo(StrictSchema):
    id: str
    name: str
    default_branch: str


class CatalogPipeline(StrictSchema):
    id: str
    name: str
    runs: int | None = None
    success_rate: str | None = None
