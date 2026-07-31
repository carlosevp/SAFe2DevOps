from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin_or_dev_mock
from app.schemas.enterprise import (
    EnterpriseStandardIn,
    EnterpriseStandardOut,
    EnterpriseStandardUpdate,
    StandardsImportBundle,
)
from app.services.enterprise_standards import EnterpriseStandardsService

router = APIRouter(prefix="/enterprise-standards", tags=["enterprise-standards"])


@router.get("", response_model=list[EnterpriseStandardOut])
def list_standards(
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[EnterpriseStandardOut]:
    return EnterpriseStandardsService(db).list_standards(
        search=search, category=category, active=active
    )


@router.post("", response_model=EnterpriseStandardOut)
def create_standard(
    body: EnterpriseStandardIn,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EnterpriseStandardOut:
    out = EnterpriseStandardsService(db).create_standard(body, actor=admin.get("subject", "admin"))
    db.commit()
    return out


@router.get("/export")
def export_standards(
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    return JSONResponse(EnterpriseStandardsService(db).export_bundle())


@router.post("/import", response_model=list[EnterpriseStandardOut])
def import_standards(
    body: StandardsImportBundle,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> list[EnterpriseStandardOut]:
    out = EnterpriseStandardsService(db).import_bundle(
        body.standards, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.get("/{standard_id}", response_model=EnterpriseStandardOut)
def get_standard(
    standard_id: str,
    _: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EnterpriseStandardOut:
    return EnterpriseStandardsService(db).get_standard(standard_id)


@router.put("/{standard_id}", response_model=EnterpriseStandardOut)
def update_standard(
    standard_id: str,
    body: EnterpriseStandardUpdate,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EnterpriseStandardOut:
    out = EnterpriseStandardsService(db).update_standard(
        standard_id, body, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.post("/{standard_id}/duplicate", response_model=EnterpriseStandardOut)
def duplicate_standard(
    standard_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EnterpriseStandardOut:
    out = EnterpriseStandardsService(db).duplicate(standard_id, actor=admin.get("subject", "admin"))
    db.commit()
    return out


@router.post("/{standard_id}/activate", response_model=EnterpriseStandardOut)
def activate_standard(
    standard_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EnterpriseStandardOut:
    out = EnterpriseStandardsService(db).set_active(
        standard_id, active=True, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.post("/{standard_id}/deactivate", response_model=EnterpriseStandardOut)
def deactivate_standard(
    standard_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> EnterpriseStandardOut:
    out = EnterpriseStandardsService(db).set_active(
        standard_id, active=False, actor=admin.get("subject", "admin")
    )
    db.commit()
    return out


@router.delete("/{standard_id}", status_code=204)
def delete_standard(
    standard_id: str,
    admin: dict[str, str] = Depends(require_admin_or_dev_mock),
    db: Session = Depends(get_db_session),
) -> None:
    EnterpriseStandardsService(db).delete_standard(standard_id, actor=admin.get("subject", "admin"))
    db.commit()
