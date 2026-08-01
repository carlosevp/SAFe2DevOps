from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.diagnostics import TimedOperation, emit_integration_event
from app.integrations.factory import get_ado_provider, get_jira_provider
from app.models import IntegrationConfiguration
from app.services.integration_config import IntegrationConfigService


def _default_jira_capabilities() -> dict[str, Any]:
    return {
        "configured": False,
        "credentials_decryptable": False,
        "identity_authenticated": False,
        "project_catalog_accessible": False,
        "issue_search_accessible": None,
        "last_catalog_refresh_status": None,
        "last_catalog_refresh_at": None,
        "last_successful_catalog_refresh_at": None,
        "last_error_category": None,
        "enabled_by_admin": True,
    }


def _default_ado_capabilities() -> dict[str, Any]:
    return {
        "configured": False,
        "credentials_decryptable": False,
        "organization_accessible": False,
        "project_catalog_accessible": False,
        "repository_catalog_accessible": False,
        "pipeline_catalog_accessible": False,
        "last_catalog_refresh_status": None,
        "last_catalog_refresh_at": None,
        "last_successful_catalog_refresh_at": None,
        "last_error_category": None,
        "enabled_by_admin": True,
    }


def compute_setup_availability(
    *,
    configured: bool,
    enabled_by_admin: bool,
    credentials_decryptable: bool,
    catalog: list[Any],
    last_refresh_status: str | None,
    catalog_stale: bool,
) -> str:
    """UI readiness for new-assessment selectors."""
    if not configured:
        return "not_configured"
    if not enabled_by_admin:
        return "administratively_disabled"
    if not credentials_decryptable:
        return "credentials_undecryptable"
    if catalog:
        if last_refresh_status == "failed" or catalog_stale:
            return "refresh_failed_cached_available"
        if catalog_stale:
            return "ready_cached"
        return "ready"
    if last_refresh_status == "success":
        return "credentials_accepted_no_projects"
    if last_refresh_status == "failed":
        return "temporarily_unavailable"
    return "configured_loading_catalog"


class IntegrationCatalogService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.cfg = IntegrationConfigService(db)
        self.settings = get_settings()

    def get_record(self) -> IntegrationConfiguration:
        return self.cfg.get()

    def jira_catalog(self, record: IntegrationConfiguration | None = None) -> list[dict[str, Any]]:
        record = record or self.get_record()
        try:
            return json.loads(record.jira_catalog_json or "[]")
        except json.JSONDecodeError:
            return []

    def ado_catalog(self, record: IntegrationConfiguration | None = None) -> list[dict[str, Any]]:
        record = record or self.get_record()
        try:
            return json.loads(record.ado_catalog_json or "[]")
        except json.JSONDecodeError:
            return []

    def build_jira_capabilities(self, record: IntegrationConfiguration) -> dict[str, Any]:
        caps = _default_jira_capabilities()
        try:
            stored = json.loads(record.jira_capabilities_json or "{}")
            if isinstance(stored, dict):
                caps.update(stored)
        except json.JSONDecodeError:
            pass
        caps["configured"] = bool(
            record.jira_site_url
            and record.jira_service_account_email
            and record.jira_api_token_encrypted
        )
        caps["enabled_by_admin"] = bool(getattr(record, "jira_enabled_by_admin", True))
        caps["last_catalog_refresh_status"] = record.jira_last_catalog_refresh_status
        caps["last_catalog_refresh_at"] = (
            record.jira_last_catalog_refresh_at.isoformat()
            if record.jira_last_catalog_refresh_at
            else None
        )
        caps["last_successful_catalog_refresh_at"] = (
            record.jira_last_successful_catalog_refresh_at.isoformat()
            if record.jira_last_successful_catalog_refresh_at
            else None
        )
        caps["last_error_category"] = record.jira_last_error_category
        # Decryptability probe without logging secrets.
        if caps["configured"]:
            try:
                _ = self.cfg.reveal_jira_token(record)
                caps["credentials_decryptable"] = True
            except AppError:
                caps["credentials_decryptable"] = False
                caps["last_error_category"] = "secret_decrypt_failed"
        return caps

    def build_ado_capabilities(self, record: IntegrationConfiguration) -> dict[str, Any]:
        caps = _default_ado_capabilities()
        try:
            stored = json.loads(record.ado_capabilities_json or "{}")
            if isinstance(stored, dict):
                caps.update(stored)
        except json.JSONDecodeError:
            pass
        caps["configured"] = bool(record.ado_org_url and record.ado_pat_encrypted)
        caps["enabled_by_admin"] = bool(getattr(record, "ado_enabled_by_admin", True))
        caps["last_catalog_refresh_status"] = record.ado_last_catalog_refresh_status
        caps["last_catalog_refresh_at"] = (
            record.ado_last_catalog_refresh_at.isoformat()
            if record.ado_last_catalog_refresh_at
            else None
        )
        caps["last_successful_catalog_refresh_at"] = (
            record.ado_last_successful_catalog_refresh_at.isoformat()
            if record.ado_last_successful_catalog_refresh_at
            else None
        )
        caps["last_error_category"] = record.ado_last_error_category
        if caps["configured"]:
            try:
                _ = self.cfg.reveal_ado_pat(record)
                caps["credentials_decryptable"] = True
            except AppError:
                caps["credentials_decryptable"] = False
                caps["last_error_category"] = "secret_decrypt_failed"
        return caps

    def setup_state(self, record: IntegrationConfiguration | None = None) -> dict[str, Any]:
        record = record or self.get_record()
        jira_caps = self.build_jira_capabilities(record)
        ado_caps = self.build_ado_capabilities(record)
        jira_catalog = self.jira_catalog(record)
        ado_catalog = self.ado_catalog(record)
        mock_mode = self.settings.integration_provider == "mock"
        if mock_mode:
            jira_caps["configured"] = True
            jira_caps["credentials_decryptable"] = True
            jira_caps["identity_authenticated"] = True
            jira_caps["project_catalog_accessible"] = True
            ado_caps["configured"] = True
            ado_caps["credentials_decryptable"] = True
            ado_caps["organization_accessible"] = True
            ado_caps["project_catalog_accessible"] = True
        jira_availability = compute_setup_availability(
            configured=bool(jira_caps["configured"]) or mock_mode,
            enabled_by_admin=bool(jira_caps["enabled_by_admin"]),
            credentials_decryptable=bool(jira_caps["credentials_decryptable"]) or mock_mode,
            catalog=jira_catalog,
            last_refresh_status=record.jira_last_catalog_refresh_status
            or ("success" if mock_mode and jira_catalog else None),
            catalog_stale=bool(record.jira_catalog_stale),
        )
        ado_availability = compute_setup_availability(
            configured=bool(ado_caps["configured"]) or mock_mode,
            enabled_by_admin=bool(ado_caps["enabled_by_admin"]),
            credentials_decryptable=bool(ado_caps["credentials_decryptable"]) or mock_mode,
            catalog=ado_catalog,
            last_refresh_status=record.ado_last_catalog_refresh_status
            or ("success" if mock_mode and ado_catalog else None),
            catalog_stale=bool(record.ado_catalog_stale),
        )
        if mock_mode and not jira_catalog:
            jira_availability = "configured_loading_catalog"
        if mock_mode and not ado_catalog:
            ado_availability = "configured_loading_catalog"
        # Zero-project success is a distinct permission/data state.
        if (
            jira_availability == "credentials_accepted_no_projects"
            or (
                jira_caps.get("project_catalog_accessible")
                and jira_caps.get("visible_project_count") == 0
                and not jira_catalog
            )
        ):
            jira_availability = "credentials_accepted_no_projects"
        return {
            "jira": {
                "availability": jira_availability,
                "capabilities": jira_caps,
                "catalog_stale": bool(record.jira_catalog_stale),
                "catalog_count": len(jira_catalog),
                "selectable": jira_availability
                in {
                    "ready",
                    "ready_cached",
                    "refresh_failed_cached_available",
                    "configured_loading_catalog",
                }
                or (bool(jira_catalog) and jira_availability != "administratively_disabled"),
            },
            "ado": {
                "availability": ado_availability,
                "capabilities": ado_caps,
                "catalog_stale": bool(record.ado_catalog_stale),
                "catalog_count": len(ado_catalog),
                "selectable": ado_availability
                in {
                    "ready",
                    "ready_cached",
                    "refresh_failed_cached_available",
                    "configured_loading_catalog",
                }
                or (bool(ado_catalog) and ado_availability != "administratively_disabled"),
            },
        }

    def refresh_jira(self) -> IntegrationConfiguration:
        record = self.get_record()
        timed = TimedOperation()
        emit_integration_event(
            "integration.catalog_refresh.started",
            provider="jira",
            integration_config_id=record.id,
            operation="catalog_refresh",
        )
        previous = self.jira_catalog(record)
        try:
            provider = get_jira_provider(self.db, self.settings)
            projects = provider.list_projects()
            payload = [
                {
                    "id": p.id,
                    "key": p.key,
                    "name": p.name,
                    "project_type_key": getattr(p, "project_type_key", None),
                    "style": getattr(p, "style", None),
                }
                for p in projects
            ]
            now = datetime.now(UTC)
            record.jira_catalog_json = json.dumps(payload)
            record.jira_catalog_stale = False
            record.jira_last_catalog_refresh_status = "success"
            record.jira_last_catalog_refresh_at = now
            record.jira_last_successful_catalog_refresh_at = now
            record.jira_last_error = None
            record.jira_last_error_category = None
            caps = self.build_jira_capabilities(record)
            caps.update(
                {
                    "identity_authenticated": True,
                    "project_catalog_accessible": True,
                    "credentials_decryptable": True,
                    "visible_project_count": len(payload),
                    "last_error_category": None
                    if payload
                    else "no_visible_projects",
                }
            )
            record.jira_capabilities_json = json.dumps(caps)
            record.catalog_refreshed_at = now
            self.db.flush()
            emit_integration_event(
                "integration.catalog_refresh.completed",
                provider="jira",
                integration_config_id=record.id,
                operation="catalog_refresh",
                total_records=len(payload),
                elapsed_ms=timed.elapsed_ms(),
                last_successful_refresh_at=now.isoformat(),
            )
            return record
        except AppError as exc:
            now = datetime.now(UTC)
            record.jira_last_catalog_refresh_status = "failed"
            record.jira_last_catalog_refresh_at = now
            record.jira_last_error = exc.message
            record.jira_last_error_category = (exc.details or {}).get("error_category") or exc.code
            if previous:
                record.jira_catalog_stale = True
                emit_integration_event(
                    "integration.catalog_cache.stale",
                    provider="jira",
                    integration_config_id=record.id,
                    operation="catalog_refresh",
                    total_records=len(previous),
                    last_successful_refresh_at=(
                        record.jira_last_successful_catalog_refresh_at.isoformat()
                        if record.jira_last_successful_catalog_refresh_at
                        else None
                    ),
                )
            self.db.flush()
            emit_integration_event(
                "integration.catalog_refresh.failed",
                provider="jira",
                integration_config_id=record.id,
                operation="catalog_refresh",
                error_category=record.jira_last_error_category,
                sanitized_external_error=exc.message,
                elapsed_ms=timed.elapsed_ms(),
            )
            raise

    def refresh_ado(self) -> IntegrationConfiguration:
        record = self.get_record()
        timed = TimedOperation()
        emit_integration_event(
            "integration.catalog_refresh.started",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="catalog_refresh",
        )
        previous = self.ado_catalog(record)
        try:
            provider = get_ado_provider(self.db, self.settings)
            projects = provider.list_projects()
            payload = [{"id": p.id, "name": p.name} for p in projects]
            now = datetime.now(UTC)
            record.ado_catalog_json = json.dumps(payload)
            record.ado_catalog_stale = False
            record.ado_last_catalog_refresh_status = "success"
            record.ado_last_catalog_refresh_at = now
            record.ado_last_successful_catalog_refresh_at = now
            record.ado_last_error = None
            record.ado_last_error_category = None
            caps = self.build_ado_capabilities(record)
            caps.update(
                {
                    "organization_accessible": True,
                    "project_catalog_accessible": True,
                    "credentials_decryptable": True,
                    "visible_project_count": len(payload),
                    "last_error_category": None if payload else "no_visible_projects",
                }
            )
            record.ado_capabilities_json = json.dumps(caps)
            record.catalog_refreshed_at = now
            self.db.flush()
            emit_integration_event(
                "integration.catalog_refresh.completed",
                provider="azure_devops",
                integration_config_id=record.id,
                operation="catalog_refresh",
                total_records=len(payload),
                elapsed_ms=timed.elapsed_ms(),
                last_successful_refresh_at=now.isoformat(),
            )
            return record
        except AppError as exc:
            now = datetime.now(UTC)
            record.ado_last_catalog_refresh_status = "failed"
            record.ado_last_catalog_refresh_at = now
            record.ado_last_error = exc.message
            record.ado_last_error_category = (exc.details or {}).get("error_category") or exc.code
            if previous:
                record.ado_catalog_stale = True
                emit_integration_event(
                    "integration.catalog_cache.stale",
                    provider="azure_devops",
                    integration_config_id=record.id,
                    operation="catalog_refresh",
                    total_records=len(previous),
                    last_successful_refresh_at=(
                        record.ado_last_successful_catalog_refresh_at.isoformat()
                        if record.ado_last_successful_catalog_refresh_at
                        else None
                    ),
                )
            self.db.flush()
            emit_integration_event(
                "integration.catalog_refresh.failed",
                provider="azure_devops",
                integration_config_id=record.id,
                operation="catalog_refresh",
                error_category=record.ado_last_error_category,
                sanitized_external_error=exc.message,
                elapsed_ms=timed.elapsed_ms(),
            )
            raise

    def refresh_all(self) -> IntegrationConfiguration:
        """Refresh both providers independently; retain caches on partial failure."""
        errors: list[str] = []
        try:
            self.refresh_jira()
        except AppError as exc:
            errors.append(f"jira:{exc.message}")
        try:
            self.refresh_ado()
        except AppError as exc:
            errors.append(f"ado:{exc.message}")
        record = self.get_record()
        if errors and not (self.jira_catalog(record) or self.ado_catalog(record)):
            raise AppError(
                code="catalog_refresh_failed",
                message="; ".join(errors),
                status_code=502,
                details={"error_category": "catalog_refresh_failed"},
            )
        return record

    def list_jira_projects_for_ui(self) -> list[dict[str, Any]]:
        record = self.get_record()
        cached = self.jira_catalog(record)
        if cached:
            emit_integration_event(
                "integration.catalog_cache.used",
                provider="jira",
                integration_config_id=record.id,
                operation="list_jira_projects",
                total_records=len(cached),
                catalog_stale=bool(record.jira_catalog_stale),
            )
            return cached
        # Auto-refresh when empty and configured.
        if record.jira_api_token_encrypted or self.settings.integration_provider == "mock":
            try:
                self.refresh_jira()
                self.db.commit()
                return self.jira_catalog()
            except AppError:
                self.db.commit()
                return []
        return []

    def list_ado_projects_for_ui(self) -> list[dict[str, Any]]:
        record = self.get_record()
        cached = self.ado_catalog(record)
        if cached:
            emit_integration_event(
                "integration.catalog_cache.used",
                provider="azure_devops",
                integration_config_id=record.id,
                operation="list_ado_projects",
                total_records=len(cached),
                catalog_stale=bool(record.ado_catalog_stale),
            )
            return cached
        if record.ado_pat_encrypted or self.settings.integration_provider == "mock":
            try:
                self.refresh_ado()
                self.db.commit()
                return self.ado_catalog()
            except AppError:
                self.db.commit()
                return []
        return []
