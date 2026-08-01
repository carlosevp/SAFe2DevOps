"""Structured integration diagnostics emitted as JSON lines to stdout/stderr."""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.logging import redact_secrets

_request_id_var: ContextVar[str | None] = ContextVar("integration_request_id", default=None)
logger = logging.getLogger("app.integrations.diagnostics")

INTEGRATION_EVENTS = frozenset(
    {
        "integration.configuration.loaded",
        "integration.credential.decrypt.started",
        "integration.credential.decrypt.succeeded",
        "integration.credential.decrypt.failed",
        "integration.connection_test.started",
        "integration.connection_test.completed",
        "integration.capability_check.started",
        "integration.capability_check.completed",
        "integration.catalog_refresh.started",
        "integration.catalog_refresh.completed",
        "integration.catalog_refresh.failed",
        "integration.external_request.completed",
        "integration.external_request.failed",
        "integration.catalog_cache.used",
        "integration.catalog_cache.stale",
    }
)


def set_integration_request_id(request_id: str | None) -> None:
    _request_id_var.set(request_id)


def get_integration_request_id() -> str | None:
    return _request_id_var.get()


def _level_for(event: str, *, ok: bool | None = None) -> int:
    settings = get_settings()
    configured = (settings.integration_log_level or settings.log_level or "INFO").upper()
    base = getattr(logging, configured, logging.INFO)
    if event.endswith(".failed") or ok is False:
        return max(base, logging.WARNING)
    if event.endswith(".stale"):
        return max(base, logging.INFO)
    return base


def emit_integration_event(event: str, **fields: Any) -> None:
    """Emit one structured JSON diagnostic event (secrets redacted)."""
    if event not in INTEGRATION_EVENTS:
        event = "integration.external_request.completed"
    payload: dict[str, Any] = {
        "event": event,
        "ts": datetime.now(UTC).isoformat(),
        "request_id": fields.pop("request_id", None) or get_integration_request_id(),
    }
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
        else:
            payload[key] = redact_secrets(value)
    # Never allow credential-looking keys through even if callers slip.
    for banned in (
        "api_token",
        "pat",
        "authorization",
        "password",
        "data_encryption_key",
        "token",
        "ciphertext",
        "plaintext",
    ):
        payload.pop(banned, None)
    line = json.dumps(payload, default=str, separators=(",", ":"))
    logger.log(
        _level_for(event, ok=fields.get("ok") if "ok" in fields else None),
        line,
        extra={"request_id": payload.get("request_id") or "-"},
    )


class TimedOperation:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
