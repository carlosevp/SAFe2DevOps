from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.factory import get_integration_providers
from app.integrations.http import validate_https_url
from app.schemas.integrations import (
    AdoCredentialsIn,
    CatalogPipeline,
    CatalogProject,
    CatalogRepo,
    ConnectionTestResult,
    IntegrationStatusOut,
    JiraCredentialsIn,
)
from app.services.integration_config import IntegrationConfigService

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _status_out(db: Session) -> IntegrationStatusOut:
    settings = get_settings()
    record = IntegrationConfigService(db).get()
    return IntegrationStatusOut(
        jira_site_url=record.jira_site_url,
        jira_service_account_email=record.jira_service_account_email,
        jira_token_configured=bool(record.jira_api_token_encrypted),
        jira_status=record.jira_status,
        jira_last_validated_at=record.jira_last_validated_at,
        jira_last_error=record.jira_last_error,
        ado_org_url=record.ado_org_url,
        ado_pat_configured=bool(record.ado_pat_encrypted),
        ado_status=record.ado_status,
        ado_last_validated_at=record.ado_last_validated_at,
        ado_last_error=record.ado_last_error,
        catalog_refreshed_at=record.catalog_refreshed_at,
        provider_mode=settings.integration_provider,
    )


@router.get("", response_model=IntegrationStatusOut)
def get_integrations(_: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)) -> IntegrationStatusOut:
    return _status_out(db)


@router.put("/jira", response_model=IntegrationStatusOut)
def save_jira(
    body: JiraCredentialsIn,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    service = IntegrationConfigService(db)
    service.update_credentials(
        jira_site_url=body.site_url,
        jira_service_account_email=body.service_account_email,
        jira_api_token=body.api_token,
    )
    db.commit()
    return _status_out(db)


@router.put("/ado", response_model=IntegrationStatusOut)
def save_ado(
    body: AdoCredentialsIn,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> IntegrationStatusOut:
    service = IntegrationConfigService(db)
    service.update_credentials(ado_org_url=body.org_url, ado_pat=body.pat)
    db.commit()
    return _status_out(db)


@router.post("/jira/test", response_model=ConnectionTestResult)
def test_jira(_: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)) -> ConnectionTestResult:
    settings = get_settings()
    service = IntegrationConfigService(db)
    record = service.get()
    try:
        if settings.integration_provider == "live":
            if not record.jira_site_url or not record.jira_api_token_encrypted:
                raise AppError(code="jira_not_configured", message="Jira is not configured", status_code=400)
            validate_https_url(record.jira_site_url, label="Jira site URL")
        providers = get_integration_providers(db, settings)
        result = providers.jira.test_connection()
        service.mark_validated(system="jira", ok=True)
        db.commit()
        return ConnectionTestResult(
            ok=True,
            system="jira",
            message=f"Connected as {result.get('display_name', 'service account')}",
            tested_at=datetime.now(UTC),
        )
    except AppError as exc:
        service.mark_validated(system="jira", ok=False, error=exc.message)
        db.commit()
        raise


@router.post("/ado/test", response_model=ConnectionTestResult)
def test_ado(_: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)) -> ConnectionTestResult:
    settings = get_settings()
    service = IntegrationConfigService(db)
    try:
        if settings.integration_provider == "live":
            record = service.get()
            if not record.ado_org_url or not record.ado_pat_encrypted:
                raise AppError(code="ado_not_configured", message="Azure DevOps is not configured", status_code=400)
            validate_https_url(record.ado_org_url, label="Azure DevOps organization URL")
        providers = get_integration_providers(db, settings)
        result = providers.ado.test_connection()
        service.mark_validated(system="ado", ok=True)
        db.commit()
        return ConnectionTestResult(
            ok=True,
            system="ado",
            message=f"Connected to {result.get('organization', 'organization')}",
            tested_at=datetime.now(UTC),
        )
    except AppError as exc:
        service.mark_validated(system="ado", ok=False, error=exc.message)
        db.commit()
        raise


@router.post("/catalog/refresh", response_model=IntegrationStatusOut)
def refresh_catalog(_: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)) -> IntegrationStatusOut:
    providers = get_integration_providers(db)
    # Touch providers to validate availability.
    providers.jira.list_projects()
    providers.ado.list_projects()
    record = IntegrationConfigService(db).get()
    record.catalog_refreshed_at = datetime.now(UTC)
    db.commit()
    return _status_out(db)


@router.get("/catalog/jira/projects", response_model=list[CatalogProject])
def jira_projects(_: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)) -> list[CatalogProject]:
    projects = get_integration_providers(db).jira.list_projects()
    return [CatalogProject(id=p.id, key=p.key, name=p.name) for p in projects]


@router.get("/catalog/jira/projects/{project_key}/boards", response_model=list[CatalogProject])
def jira_boards(
    project_key: str, _: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)
) -> list[CatalogProject]:
    boards = get_integration_providers(db).jira.list_boards(project_key)
    return [CatalogProject(id=b.id, key=project_key, name=b.name) for b in boards]


@router.get("/catalog/ado/projects", response_model=list[CatalogProject])
def ado_projects(_: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)) -> list[CatalogProject]:
    projects = get_integration_providers(db).ado.list_projects()
    return [CatalogProject(id=p.id, name=p.name) for p in projects]


@router.get("/catalog/ado/projects/{project_id}/repositories", response_model=list[CatalogRepo])
def ado_repos(
    project_id: str, _: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)
) -> list[CatalogRepo]:
    repos = get_integration_providers(db).ado.list_repositories(project_id)
    return [CatalogRepo(id=r.id, name=r.name, default_branch=r.default_branch) for r in repos]


@router.get("/catalog/ado/projects/{project_id}/repositories/{repo_id}/branches", response_model=list[str])
def ado_branches(
    project_id: str, repo_id: str, _: dict = Depends(require_admin_or_dev_mock), db: Session = Depends(get_db_session)
) -> list[str]:
    return get_integration_providers(db).ado.list_branches(project_id, repo_id)


@router.get("/catalog/ado/projects/{project_id}/pipelines", response_model=list[CatalogPipeline])
def ado_pipelines(
    project_id: str,
    repository_name: str | None = None,
    _: dict = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[CatalogPipeline]:
    providers = get_integration_providers(db)
    pipelines = providers.ado.list_pipelines(project_id, repository_name)
    # Enrich with mock-friendly run stats when available.
    runs = providers.ado.list_pipeline_runs(
        project_id=project_id,
        pipeline_names=[p.name for p in pipelines],
        lookback_days=90,
    )
    out: list[CatalogPipeline] = []
    for pipeline in pipelines:
        related = [r for r in runs if r.pipeline_name == pipeline.name]
        success = sum(1 for r in related if r.result == "succeeded")
        rate = f"{int(success / len(related) * 100)}%" if related else None
        out.append(CatalogPipeline(id=pipeline.id, name=pipeline.name, runs=len(related) or None, success_rate=rate))
    return out
