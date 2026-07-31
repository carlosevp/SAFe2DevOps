from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx

from app.core.errors import AppError
from app.core.logging import redact_secrets

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
MAX_RETRIES = 3
RETRY_STATUSES = {429, 502, 503, 504}

# Hostname suffixes accepted for live Jira Cloud / Azure DevOps integrations.
ALLOWED_INTEGRATION_HOST_SUFFIXES = (
    ".atlassian.net",
    ".jira.com",
    "dev.azure.com",
    ".visualstudio.com",
)


def validate_https_url(url: str, *, label: str) -> str:
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned.startswith("https://"):
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must use HTTPS",
            status_code=400,
            details={"label": label},
        )
    parsed = urlparse(cleaned)
    if parsed.username or parsed.password:
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must not include credentials in the URL",
            status_code=400,
            details={"label": label},
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} host is missing",
            status_code=400,
            details={"label": label},
        )
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must not target private or link-local addresses",
            status_code=400,
            details={"label": label},
        )
    if ip is None:
        allowed = host == "dev.azure.com" or any(
            host.endswith(suffix) if suffix.startswith(".") else host == suffix
            for suffix in ALLOWED_INTEGRATION_HOST_SUFFIXES
        )
        if not allowed:
            raise AppError(
                code="invalid_integration_url",
                message=f"{label} host is not an allowed Jira or Azure DevOps endpoint",
                status_code=400,
                details={"label": label},
            )
    return cleaned


def sanitize_remote_text(value: Any, *, max_len: int = 4000) -> str:
    """Treat remote text as untrusted; strip control chars and bound length."""
    text = "" if value is None else str(value)
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    # Neutralize common prompt-injection markers without changing business meaning much.
    lowered = cleaned.lower()
    for marker in ("ignore previous instructions", "system:", "<<", "```"):
        start = 0
        while True:
            idx = lowered.find(marker, start)
            if idx < 0:
                break
            cleaned = cleaned[:idx] + cleaned[idx + len(marker) :]
            lowered = cleaned.lower()
            start = idx
    return cleaned[:max_len]


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.request(method, url, params=params, json=json_body, headers=headers)
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                retry_after = float(response.headers.get("Retry-After", "1"))
                time.sleep(min(max(retry_after, 0.5), 5.0) * attempt)
                continue
            if response.status_code >= 400:
                logger.warning(
                    "integration request failed status=%s url=%s body=%s",
                    response.status_code,
                    redact_secrets(url),
                    redact_secrets(response.text[:300]),
                )
                raise AppError(
                    code="integration_http_error",
                    message="Remote integration request failed",
                    status_code=502,
                    details={"status": response.status_code},
                )
            if not response.content:
                return None
            return response.json()
        except httpx.TimeoutException as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            time.sleep(0.5 * attempt)
        except httpx.HTTPError as exc:
            last_error = exc
            break
    raise AppError(
        code="integration_unreachable",
        message="Remote integration is unreachable",
        status_code=502,
        details={"error": redact_secrets(str(last_error) if last_error else "unknown")},
    )


def with_client(base_url: str, headers: dict[str, str], fn: Callable[[httpx.Client], T]) -> T:
    with httpx.Client(
        base_url=base_url, headers=headers, timeout=DEFAULT_TIMEOUT, follow_redirects=False
    ) as client:
        return fn(client)
