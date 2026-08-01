from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ConnectionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationConfiguration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Singleton-style configuration for one Jira and one ADO environment."""

    __tablename__ = "integration_configurations"
    __table_args__ = (UniqueConstraint("singleton_key", name="uq_integration_singleton"),)

    singleton_key: Mapped[str] = mapped_column(String(32), nullable=False, default="default")

    jira_site_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    jira_service_account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    jira_api_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # classic_account_api_token | scoped_service_account_token — never inferred from token string
    jira_credential_mode: Mapped[str] = mapped_column(
        String(64), nullable=False, default="classic_account_api_token"
    )
    jira_cloud_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    jira_enabled_by_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    jira_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectionStatus.UNKNOWN.value
    )
    jira_last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jira_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_last_error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    jira_capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    jira_catalog_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    jira_catalog_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    jira_last_catalog_refresh_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    jira_last_catalog_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jira_last_successful_catalog_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    ado_org_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ado_pat_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    ado_enabled_by_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ado_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectionStatus.UNKNOWN.value
    )
    ado_last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ado_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ado_last_error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ado_capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ado_catalog_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    ado_catalog_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ado_last_catalog_refresh_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ado_last_catalog_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ado_last_successful_catalog_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    catalog_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
