from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import AuditEvent
from app.services.audit import AuditService
from app.services.integration_config import IntegrationConfigService


def test_encryption_round_trip(app_env: dict[str, str]) -> None:
    token = "super-secret-jira-token-value"
    encrypted = encrypt_secret(token)
    assert encrypted != token
    assert decrypt_secret(encrypted) == token


def test_audit_redaction(app_env: dict[str, str]) -> None:
    from app.main import create_app

    with TestClient(create_app()):
        pass
    db: Session = get_session_factory()()
    try:
        event = AuditService(db).record(
            event_type="integration.credentials_updated",
            message="Saved password=hunter2 and token=abc",
            details={
                "jira_api_token": "ATATTshouldredact",
                "ado_pat": "pat-should-redact",
                "note": "ok",
            },
        )
        db.commit()
        stored = db.get(AuditEvent, event.id)
        assert stored is not None
        assert "hunter2" not in stored.message
        details = json.loads(stored.details_json)
        assert details["jira_api_token"] == "***REDACTED***"
        assert details["ado_pat"] == "***REDACTED***"
        assert details["note"] == "ok"
    finally:
        db.close()


def test_integration_secret_round_trip(app_env: dict[str, str]) -> None:
    from app.main import create_app

    with TestClient(create_app()):
        pass
    db = get_session_factory()()
    try:
        service = IntegrationConfigService(db)
        record = service.update_credentials(
            jira_site_url="https://example.atlassian.net",
            jira_service_account_email="svc@example.com",
            jira_api_token="jira-secret-token",
            ado_org_url="https://dev.azure.com/example",
            ado_pat="ado-secret-pat",
        )
        db.commit()
        assert record.jira_api_token_encrypted != "jira-secret-token"
        assert service.reveal_jira_token(record) == "jira-secret-token"
        assert service.reveal_ado_pat(record) == "ado-secret-pat"
    finally:
        db.close()
