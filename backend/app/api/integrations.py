from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.diagnostics import emit_integration_event, set_integration_request_id
from app.integrations.factory import get_ado_provider, get_jira_provider
from app.schemas.integrations import (
    AdoCapabilitiesOut,
    AdoCredentialsIn,
    CatalogPipeline,
    CatalogProject,
    CatalogRepo,
    ConnectionTestResult,
    IntegrationDiagnosticsOut,
    IntegrationStatusOut,
    JiraCapabilitiesOut,
    JiraCredentialsIn,
    ProviderSetupStateOut,
)
from app.services.integration_catalog import IntegrationCatalogService
from app.services.integration_config import IntegrationConfigService

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _bind_request_id(request: Request) -> None:
    set_integration_request_id(getattr(request.state, "request_id", None))


def _status_out(db: Session) -> IntegrationStatusOut:
    settings = get_settings()
    catalog = IntegrationCatalogService(db)
    record = catalog.get_record()
    jira_caps = catalog.build_jira_capabilities(record)
    ado_caps = catalog.build_ado_capabilities(record)
    setup = catalog.setup_state(record)
    return IntegrationStatusOut(
        jira_site_url=record.jira_site_url,
        jira_service_account_email=record.jira_service_account_email,
        jira_token_configured=bool(record.jira_api_token_encrypted),
        jira_credential_mode=getattr(record, "jira_credential_mode", None)
        or "classic_account_api_token",
        jira_cloud_id=getattr(record, "jira_cloud_id", None),
        jira_enabled_by_admin=bool(getattr(record, "jira_enabled_by_admin", True)),
        jira_status=record.jira_status,
        jira_last_validated_at=record.jira_last_validated_at,
        jira_last_error=record.jira_last_error,
        jira_last_error_category=record.jira_last_error_category,
        jira_capabilities=JiraCapabilitiesOut(**{
            k: jira_caps.get(k)
            for k in JiraCapabilitiesOut.model_fields
            if k in jira_caps
        }),
        jira_catalog_stale=bool(record.jira_catalog_stale),
        jira_last_catalog_refresh_status=record.jira_last_catalog_refresh_status,
        jira_last_catalog_refresh_at=record.jira_last_catalog_refresh_at,
        jira_last_successful_catalog_refresh_at=record.jira_last_successful_catalog_refresh_at,
        ado_org_url=record.ado_org_url,
        ado_pat_configured=bool(record.ado_pat_encrypted),
        ado_enabled_by_admin=bool(getattr(record, "ado_enabled_by_admin", True)),
        ado_status=record.ado_status,
        ado_last_validated_at=record.ado_last_validated_at,
        ado_last_error=record.ado_last_error,
        ado_last_error_category=record.ado_last_error_category,
        ado_capabilities=AdoCapabilitiesOut(**{
            k: ado_caps.get(k) for k in AdoCapabilitiesOut.model_fields if k in ado_caps
        }),
        ado_catalog_stale=bool(record.ado_catalog_stale),
        ado_last_catalog_refresh_status=record.ado_last_catalog_refresh_status,
        ado_last_catalog_refresh_at=record.ado_last_catalog_refresh_at,
        ado_last_successful_catalog_refresh_at=record.ado_last_successful_catalog_refresh_at,
        catalog_refreshed_at=record.catalog_refreshed_at,
        provider_mode=settings.integration_provider,
        setup_state={
            "jira": ProviderSetupStateOut(**setup["jira"]),
            "ado": ProviderSetupStateOut(**setup["ado"]),
        },
        diagnostics_enabled=bool(settings.enable_admin_integration_diagnostics),
    )


@router.get("", response_model=IntegrationStatusOut)
def get_integrations(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    _bind_request_id(request)
    return _status_out(db)


@router.put("/jira", response_model=IntegrationStatusOut)
def save_jira(
    body: JiraCredentialsIn,
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    _bind_request_id(request)
    service = IntegrationConfigService(db)
    service.update_jira(
        jira_site_url=body.site_url,
        jira_service_account_email=body.service_account_email,
        jira_api_token=body.api_token,
        jira_credential_mode=body.credential_mode,
        jira_cloud_id=body.cloud_id,
        jira_enabled_by_admin=body.enabled_by_admin,
    )
    db.commit()
    return _status_out(db)


@router.put("/ado", response_model=IntegrationStatusOut)
def save_ado(
    body: AdoCredentialsIn,
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    _bind_request_id(request)
    service = IntegrationConfigService(db)
    service.update_ado(
        ado_org_url=body.org_url,
        ado_pat=body.pat,
        ado_enabled_by_admin=body.enabled_by_admin,
    )
    db.commit()
    return _status_out(db)


@router.post("/jira/test", response_model=ConnectionTestResult)
def test_jira(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ConnectionTestResult:
    _bind_request_id(request)
    settings = get_settings()
    service = IntegrationConfigService(db)
    record = service.get()
    emit_integration_event(
        "integration.connection_test.started",
        provider="jira",
        integration_config_id=record.id,
        operation="connection_test",
    )
    try:
        if settings.integration_provider == "live":
            if not record.jira_site_url or not record.jira_api_token_encrypted:
                raise AppError(
                    code="jira_not_configured",
                    message="Jira is not configured",
                    status_code=400,
                    details={"error_category": "not_configured"},
                )
        provider = get_jira_provider(db, settings)
        emit_integration_event(
            "integration.capability_check.started",
            provider="jira",
            integration_config_id=record.id,
            operation="capability_check",
        )
        caps = provider.run_capability_checks()
        emit_integration_event(
            "integration.capability_check.completed",
            provider="jira",
            integration_config_id=record.id,
            operation="capability_check",
            ok=bool(caps.identity_authenticated),
            total_records=caps.visible_project_count,
            error_category=caps.last_error_category,
        )
        ok = bool(caps.identity_authenticated)
        service.mark_validated(
            system="jira",
            ok=ok,
            error=None if ok else caps.last_error_message,
            error_category=None if ok else caps.last_error_category,
        )
        import json

        record.jira_capabilities_json = json.dumps(
            {
                "configured": caps.configured,
                "credentials_decryptable": caps.credentials_decryptable,
                "identity_authenticated": caps.identity_authenticated,
                "project_catalog_accessible": caps.project_catalog_accessible,
                "issue_search_accessible": caps.issue_search_accessible,
                "visible_project_count": caps.visible_project_count,
                "enabled_by_admin": bool(record.jira_enabled_by_admin),
                "last_error_category": caps.last_error_category,
            }
        )
        db.commit()
        message = f"Connected as {caps.display_name or 'service account'}"
        if caps.identity_authenticated and caps.visible_project_count == 0:
            message = caps.last_error_message or message
            ok = True  # auth succeeded; permission/data state is separate
        emit_integration_event(
            "integration.connection_test.completed",
            provider="jira",
            integration_config_id=record.id,
            operation="connection_test",
            ok=ok,
        )
        return ConnectionTestResult(
            ok=ok,
            system="jira",
            message=message,
            tested_at=datetime.now(UTC),
            error_category=caps.last_error_category,
            capabilities={
                "identity_authenticated": caps.identity_authenticated,
                "project_catalog_accessible": caps.project_catalog_accessible,
                "issue_search_accessible": caps.issue_search_accessible,
                "visible_project_count": caps.visible_project_count,
                "resolved_api_host": caps.resolved_api_host,
                "credential_mode": caps.credential_mode,
                "cloud_id_present": caps.cloud_id_present,
            },
        )
    except AppError as exc:
        service.mark_validated(
            system="jira",
            ok=False,
            error=exc.message,
            error_category=(exc.details or {}).get("error_category") or exc.code,
        )
        db.commit()
        emit_integration_event(
            "integration.connection_test.completed",
            provider="jira",
            integration_config_id=record.id,
            operation="connection_test",
            ok=False,
            error_category=(exc.details or {}).get("error_category") or exc.code,
            sanitized_external_error=exc.message,
        )
        raise


@router.post("/ado/test", response_model=ConnectionTestResult)
def test_ado(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> ConnectionTestResult:
    _bind_request_id(request)
    settings = get_settings()
    service = IntegrationConfigService(db)
    record = service.get()
    emit_integration_event(
        "integration.connection_test.started",
        provider="azure_devops",
        integration_config_id=record.id,
        operation="connection_test",
    )
    try:
        if settings.integration_provider == "live":
            if not record.ado_org_url or not record.ado_pat_encrypted:
                raise AppError(
                    code="ado_not_configured",
                    message="Azure DevOps is not configured",
                    status_code=400,
                    details={"error_category": "not_configured"},
                )
        provider = get_ado_provider(db, settings)
        emit_integration_event(
            "integration.capability_check.started",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="capability_check",
        )
        caps = provider.run_capability_checks()
        emit_integration_event(
            "integration.capability_check.completed",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="capability_check",
            ok=bool(caps.organization_accessible),
            total_records=caps.visible_project_count,
            error_category=caps.last_error_category,
        )
        ok = bool(caps.organization_accessible)
        service.mark_validated(
            system="ado",
            ok=ok,
            error=None if ok else caps.last_error_message,
            error_category=None if ok else caps.last_error_category,
        )
        import json

        record.ado_capabilities_json = json.dumps(
            {
                "configured": caps.configured,
                "credentials_decryptable": caps.credentials_decryptable,
                "organization_accessible": caps.organization_accessible,
                "project_catalog_accessible": caps.project_catalog_accessible,
                "repository_catalog_accessible": caps.repository_catalog_accessible,
                "pipeline_catalog_accessible": caps.pipeline_catalog_accessible,
                "visible_project_count": caps.visible_project_count,
                "enabled_by_admin": bool(record.ado_enabled_by_admin),
                "last_error_category": caps.last_error_category,
            }
        )
        db.commit()
        message = f"Connected to {caps.organization or 'organization'}"
        if ok and caps.visible_project_count == 0:
            message = caps.last_error_message or message
        emit_integration_event(
            "integration.connection_test.completed",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="connection_test",
            ok=ok,
        )
        return ConnectionTestResult(
            ok=ok,
            system="ado",
            message=message,
            tested_at=datetime.now(UTC),
            error_category=caps.last_error_category,
            capabilities={
                "organization_accessible": caps.organization_accessible,
                "project_catalog_accessible": caps.project_catalog_accessible,
                "repository_catalog_accessible": caps.repository_catalog_accessible,
                "pipeline_catalog_accessible": caps.pipeline_catalog_accessible,
                "visible_project_count": caps.visible_project_count,
                "resolved_api_host": caps.resolved_api_host,
            },
        )
    except AppError as exc:
        service.mark_validated(
            system="ado",
            ok=False,
            error=exc.message,
            error_category=(exc.details or {}).get("error_category") or exc.code,
        )
        db.commit()
        emit_integration_event(
            "integration.connection_test.completed",
            provider="azure_devops",
            integration_config_id=record.id,
            operation="connection_test",
            ok=False,
            error_category=(exc.details or {}).get("error_category") or exc.code,
            sanitized_external_error=exc.message,
        )
        raise


@router.post("/catalog/refresh", response_model=IntegrationStatusOut)
def refresh_catalog(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    _bind_request_id(request)
    catalog = IntegrationCatalogService(db)
    catalog.refresh_all()
    db.commit()
    return _status_out(db)


@router.post("/catalog/refresh/jira", response_model=IntegrationStatusOut)
def refresh_jira_catalog(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    _bind_request_id(request)
    IntegrationCatalogService(db).refresh_jira()
    db.commit()
    return _status_out(db)


@router.post("/catalog/refresh/ado", response_model=IntegrationStatusOut)
def refresh_ado_catalog(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    _bind_request_id(request)
    IntegrationCatalogService(db).refresh_ado()
    db.commit()
    return _status_out(db)


@router.get("/catalog/jira/projects", response_model=list[CatalogProject])
def jira_projects(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[CatalogProject]:
    _bind_request_id(request)
    rows = IntegrationCatalogService(db).list_jira_projects_for_ui()
    return [
        CatalogProject(
            id=str(p.get("id")),
            key=p.get("key"),
            name=str(p.get("name") or ""),
            project_type_key=p.get("project_type_key"),
            style=p.get("style"),
        )
        for p in rows
    ]


@router.get("/catalog/jira/projects/{project_key}/boards", response_model=list[CatalogProject])
def jira_boards(
    project_key: str,
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[CatalogProject]:
    _bind_request_id(request)
    boards = get_jira_provider(db).list_boards(project_key)
    return [CatalogProject(id=b.id, key=project_key, name=b.name) for b in boards]


@router.get("/catalog/ado/projects", response_model=list[CatalogProject])
def ado_projects(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[CatalogProject]:
    _bind_request_id(request)
    rows = IntegrationCatalogService(db).list_ado_projects_for_ui()
    return [CatalogProject(id=str(p.get("id")), name=str(p.get("name") or "")) for p in rows]


@router.get("/catalog/ado/projects/{project_id}/repositories", response_model=list[CatalogRepo])
def ado_repos(
    project_id: str,
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[CatalogRepo]:
    _bind_request_id(request)
    repos = get_ado_provider(db).list_repositories(project_id)
    return [CatalogRepo(id=r.id, name=r.name, default_branch=r.default_branch) for r in repos]


@router.get(
    "/catalog/ado/projects/{project_id}/repositories/{repo_id}/branches", response_model=list[str]
)
def ado_branches(
    project_id: str,
    repo_id: str,
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[str]:
    _bind_request_id(request)
    return get_ado_provider(db).list_branches(project_id, repo_id)


@router.get("/catalog/ado/projects/{project_id}/pipelines", response_model=list[CatalogPipeline])
def ado_pipelines(
    project_id: str,
    request: Request,
    repository_name: str | None = None,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[CatalogPipeline]:
    _bind_request_id(request)
    provider = get_ado_provider(db)
    pipelines = provider.list_pipelines(project_id, repository_name)
    # Keep listing lightweight; run stats are optional enrichment.
    out: list[CatalogPipeline] = []
    try:
        runs = provider.list_pipeline_runs(
            project_id=project_id,
            pipeline_names=[p.name for p in pipelines],
            lookback_days=90,
        )
    except AppError:
        runs = []
    for pipeline in pipelines:
        related = [r for r in runs if r.pipeline_name == pipeline.name]
        success = sum(1 for r in related if r.result == "succeeded")
        rate = f"{int(success / len(related) * 100)}%" if related else None
        out.append(
            CatalogPipeline(
                id=pipeline.id, name=pipeline.name, runs=len(related) or None, success_rate=rate
            )
        )
    return out


@router.get("/setup-state")
def setup_state(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> dict:
    _bind_request_id(request)
    return IntegrationCatalogService(db).setup_state()


@router.post("/diagnostics/jira", response_model=IntegrationDiagnosticsOut)
def diagnostics_jira(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationDiagnosticsOut:
    _bind_request_id(request)
    settings = get_settings()
    if not settings.enable_admin_integration_diagnostics:
        raise AppError(
            code="diagnostics_disabled",
            message="Admin integration diagnostics are disabled",
            status_code=403,
        )
    record = IntegrationConfigService(db).get()
    provider = get_jira_provider(db, settings)
    caps = provider.run_capability_checks()
    return IntegrationDiagnosticsOut(
        provider="jira",
        configured_site_or_org=record.jira_site_url,
        resolved_api_host=caps.resolved_api_host,
        cloud_id_present=caps.cloud_id_present,
        credential_mode=caps.credential_mode,
        identity_test="pass" if caps.identity_authenticated else "fail",
        project_catalog_test="pass" if caps.project_catalog_accessible else "fail",
        issue_search_test=(
            "pass"
            if caps.issue_search_accessible
            else ("skip" if caps.issue_search_accessible is None else "fail")
        ),
        visible_project_count=caps.visible_project_count,
        last_successful_refresh_at=record.jira_last_successful_catalog_refresh_at,
        error_category=caps.last_error_category,
        corrective_action=caps.corrective_action,
        message=caps.last_error_message,
        capabilities={
            "identity_authenticated": caps.identity_authenticated,
            "project_catalog_accessible": caps.project_catalog_accessible,
            "issue_search_accessible": caps.issue_search_accessible,
        },
    )


@router.post("/diagnostics/ado", response_model=IntegrationDiagnosticsOut)
def diagnostics_ado(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationDiagnosticsOut:
    _bind_request_id(request)
    settings = get_settings()
    if not settings.enable_admin_integration_diagnostics:
        raise AppError(
            code="diagnostics_disabled",
            message="Admin integration diagnostics are disabled",
            status_code=403,
        )
    record = IntegrationConfigService(db).get()
    provider = get_ado_provider(db, settings)
    caps = provider.run_capability_checks()
    return IntegrationDiagnosticsOut(
        provider="azure_devops",
        configured_site_or_org=record.ado_org_url,
        resolved_api_host=caps.resolved_api_host,
        identity_test="pass" if caps.organization_accessible else "fail",
        project_catalog_test="pass" if caps.project_catalog_accessible else "fail",
        repository_test="pass" if caps.repository_catalog_accessible else "fail",
        pipeline_build_test="pass" if caps.pipeline_catalog_accessible else "fail",
        visible_project_count=caps.visible_project_count,
        last_successful_refresh_at=record.ado_last_successful_catalog_refresh_at,
        error_category=caps.last_error_category,
        corrective_action=caps.corrective_action,
        message=caps.last_error_message,
        capabilities={
            "organization_accessible": caps.organization_accessible,
            "project_catalog_accessible": caps.project_catalog_accessible,
            "repository_catalog_accessible": caps.repository_catalog_accessible,
            "pipeline_catalog_accessible": caps.pipeline_catalog_accessible,
        },
    )


@router.post("/diagnostics/network")
def diagnostics_network(
    request: Request,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> dict:
    """Admin-only probe of configured Jira/ADO hosts (not a generic URL fetch)."""
    _bind_request_id(request)
    settings = get_settings()
    if not settings.enable_admin_integration_diagnostics:
        raise AppError(
            code="diagnostics_disabled",
            message="Admin integration diagnostics are disabled",
            status_code=403,
        )
    results: dict[str, object] = {}
    try:
        jira = get_jira_provider(db, settings)
        caps = jira.run_capability_checks()
        results["jira"] = {
            "ok": caps.identity_authenticated,
            "host": caps.resolved_api_host,
            "error_category": caps.last_error_category,
        }
    except AppError as exc:
        results["jira"] = {
            "ok": False,
            "error_category": (exc.details or {}).get("error_category") or exc.code,
            "message": exc.message,
        }
    try:
        ado = get_ado_provider(db, settings)
        caps = ado.run_capability_checks()
        results["azure_devops"] = {
            "ok": caps.organization_accessible,
            "host": caps.resolved_api_host,
            "error_category": caps.last_error_category,
        }
    except AppError as exc:
        results["azure_devops"] = {
            "ok": False,
            "error_category": (exc.details or {}).get("error_category") or exc.code,
            "message": exc.message,
        }
    return results
