from __future__ import annotations

from app.core.logging import redact_secrets


def test_secret_redaction() -> None:
    payload = {
        "password": "super-secret",
        "openai_api_key": "sk-abcdefghijklmnopqrstuvwxyz",
        "note": "Authorization: Bearer abc.def.ghi",
        "nested": {"token": "atat_should_hide"},
    }
    redacted = redact_secrets(payload)
    assert redacted["password"] == "***REDACTED***"
    assert redacted["openai_api_key"] == "***REDACTED***"
    assert "***REDACTED***" in redacted["note"]
    assert redacted["nested"]["token"] == "***REDACTED***"

    line = redact_secrets("api_key=sk-abcdefghijklmnopqrstuvwxyz password=hunter2")
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in line
    assert "hunter2" not in line
    assert "***REDACTED***" in line
