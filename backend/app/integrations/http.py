from __future__ import annotations

import ipaddress
import logging
import os
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import redact_secrets
from app.integrations.diagnostics import TimedOperation, emit_integration_event

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_RETRIES = 3
RETRY_STATUSES = {429, 502, 503, 504}

# Hostname suffixes accepted for live Jira Cloud / Azure DevOps integrations.
ALLOWED_INTEGRATION_HOST_SUFFIXES = (
    ".atlassian.net",
    ".jira.com",
    "dev.azure.com",
    ".visualstudio.com",
    "api.atlassian.com",
)

ERROR_CATEGORY_BY_STATUS = {
    401: "authentication_failed",
    403: "permission_denied",
    404: "not_found_or_wrong_base",
    429: "throttled",
    500: "provider_error",
    502: "provider_error",
    503: "provider_unavailable",
    504: "provider_timeout",
}


def integration_timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        settings.integration_http_timeout_seconds,
        connect=settings.integration_http_connect_timeout_seconds,
    )


def sanitize_host(url_or_host: str) -> str:
    raw = (url_or_host or "").strip()
    if "://" not in raw:
        return raw.split("/")[0].lower()
    parsed = urlparse(raw)
    return (parsed.hostname or "").lower()


def validate_https_url(url: str, *, label: str, allow_api_gateway: bool = False) -> str:
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned.startswith("https://"):
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must use HTTPS",
            status_code=400,
            details={"label": label, "error_category": "invalid_url"},
        )
    parsed = urlparse(cleaned)
    if parsed.username or parsed.password:
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must not include credentials in the URL",
            status_code=400,
            details={"label": label, "error_category": "invalid_url"},
        )
    if parsed.query or parsed.fragment:
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must not include query parameters or fragments",
            status_code=400,
            details={"label": label, "error_category": "invalid_url"},
        )
    path = (parsed.path or "").rstrip("/")
    if path and "/rest/api" in path.lower():
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must be the site root, not a /rest/api path",
            status_code=400,
            details={"label": label, "error_category": "invalid_url"},
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} host is missing",
            status_code=400,
            details={"label": label, "error_category": "invalid_url"},
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
            details={"label": label, "error_category": "invalid_url"},
        )
    if ip is None:
        allowed = host == "dev.azure.com" or host == "api.atlassian.com" or any(
            host.endswith(suffix) if suffix.startswith(".") else host == suffix
            for suffix in ALLOWED_INTEGRATION_HOST_SUFFIXES
        )
        if host == "api.atlassian.com" and not allow_api_gateway:
            # Callers build gateway URLs internally; admin-entered site URLs must be tenant hosts.
            raise AppError(
                code="invalid_integration_url",
                message=f"{label} must be the Jira site URL (*.atlassian.net), not api.atlassian.com",
                status_code=400,
                details={"label": label, "error_category": "invalid_url"},
            )
        if not allowed:
            raise AppError(
                code="invalid_integration_url",
                message=f"{label} host is not an allowed Jira or Azure DevOps endpoint",
                status_code=400,
                details={"label": label, "error_category": "invalid_url"},
            )
    # Keep path-less site/org roots (or allow_api_gateway resolved bases with /ex/jira/{id}).
    if allow_api_gateway and host == "api.atlassian.com":
        return cleaned
    if path and path not in {"", "/"}:
        # Azure DevOps org URLs are https://dev.azure.com/{org}
        if host == "dev.azure.com" and path.count("/") == 1:
            return cleaned
        if host.endswith(".visualstudio.com") and path in {"", "/"}:
            return cleaned
        if host == "dev.azure.com":
            return cleaned
        raise AppError(
            code="invalid_integration_url",
            message=f"{label} must not include an API path",
            status_code=400,
            details={"label": label, "error_category": "invalid_url"},
        )
    return cleaned


def normalize_jira_site_url(url: str) -> str:
    return validate_https_url(url, label="Jira site URL", allow_api_gateway=False)


def normalize_ado_org_url(value: str) -> str:
    """Accept org name, https://dev.azure.com/{org}, or legacy visualstudio URL."""
    raw = (value or "").strip().rstrip("/")
    if not raw:
        raise AppError(
            code="invalid_integration_url",
            message="Azure DevOps organization URL is required",
            status_code=400,
            details={"error_category": "invalid_url"},
        )
    if "://" not in raw and "/" not in raw and " " not in raw:
        raw = f"https://dev.azure.com/{raw}"
    cleaned = validate_https_url(raw, label="Azure DevOps organization URL")
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if host == "dev.azure.com":
        parts = [p for p in (parsed.path or "").split("/") if p]
        if len(parts) != 1:
            raise AppError(
                code="invalid_integration_url",
                message="Azure DevOps URL must be https://dev.azure.com/{organization}",
                status_code=400,
                details={"error_category": "invalid_url"},
            )
        return f"https://dev.azure.com/{parts[0]}"
    if host.endswith(".visualstudio.com"):
        org = host.split(".visualstudio.com", 1)[0]
        if not org:
            raise AppError(
                code="invalid_integration_url",
                message="Legacy Azure DevOps organization host is invalid",
                status_code=400,
                details={"error_category": "invalid_url"},
            )
        return f"https://dev.azure.com/{org}"
    raise AppError(
        code="invalid_integration_url",
        message="Azure DevOps host is not an allowed organization endpoint",
        status_code=400,
        details={"error_category": "invalid_url"},
    )


def sanitize_remote_text(value: Any, *, max_len: int = 4000) -> str:
    """Treat remote text as untrusted; strip control chars and bound length."""
    text = "" if value is None else str(value)
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
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


def classify_http_error(status: int) -> str:
    return ERROR_CATEGORY_BY_STATUS.get(status, "integration_http_error")


def _safe_error_message(response: httpx.Response) -> str:
    text = redact_secrets((response.text or "")[:240])
    return sanitize_remote_text(text, max_len=240)


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    provider: str | None = None,
    operation: str | None = None,
    endpoint_template: str | None = None,
    integration_config_id: str | None = None,
    page_number: int | None = None,
) -> Any:
    last_error: Exception | None = None
    host = sanitize_host(str(client.base_url) if client.base_url else url)
    path_template = endpoint_template or url
    for attempt in range(1, MAX_RETRIES + 1):
        timed = TimedOperation()
        try:
            response = client.request(method, url, params=params, json=json_body, headers=headers)
            elapsed = timed.elapsed_ms()
            correlation = (
                response.headers.get("x-request-id")
                or response.headers.get("x-ms-request-id")
                or response.headers.get("x-atlassian-request-id")
            )
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                retry_after = float(response.headers.get("Retry-After", "1"))
                emit_integration_event(
                    "integration.external_request.failed",
                    provider=provider,
                    operation=operation,
                    http_method=method,
                    sanitized_host=host,
                    endpoint_path_template=path_template,
                    response_status=response.status_code,
                    elapsed_ms=elapsed,
                    attempt=attempt,
                    page_number=page_number,
                    error_category=classify_http_error(response.status_code),
                    sanitized_external_error=_safe_error_message(response),
                    external_correlation_id=correlation,
                    integration_config_id=integration_config_id,
                    retrying=True,
                )
                time.sleep(min(max(retry_after, 0.5), 5.0) * attempt)
                continue
            if response.status_code >= 400:
                category = classify_http_error(response.status_code)
                emit_integration_event(
                    "integration.external_request.failed",
                    provider=provider,
                    operation=operation,
                    http_method=method,
                    sanitized_host=host,
                    endpoint_path_template=path_template,
                    response_status=response.status_code,
                    elapsed_ms=elapsed,
                    attempt=attempt,
                    page_number=page_number,
                    error_category=category,
                    sanitized_external_error=_safe_error_message(response),
                    external_correlation_id=correlation,
                    integration_config_id=integration_config_id,
                )
                raise AppError(
                    code="integration_http_error",
                    message="Remote integration request failed",
                    status_code=502,
                    details={
                        "status": response.status_code,
                        "error_category": category,
                        "provider": provider,
                        "operation": operation,
                    },
                )
            emit_integration_event(
                "integration.external_request.completed",
                provider=provider,
                operation=operation,
                http_method=method,
                sanitized_host=host,
                endpoint_path_template=path_template,
                response_status=response.status_code,
                elapsed_ms=elapsed,
                attempt=attempt,
                page_number=page_number,
                external_correlation_id=correlation,
                integration_config_id=integration_config_id,
            )
            if not response.content:
                return None
            return response.json()
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            last_error = exc
            emit_integration_event(
                "integration.external_request.failed",
                provider=provider,
                operation=operation,
                http_method=method,
                sanitized_host=host,
                endpoint_path_template=path_template,
                elapsed_ms=timed.elapsed_ms(),
                attempt=attempt,
                page_number=page_number,
                error_category="network_timeout",
                sanitized_external_error=redact_secrets(str(exc)),
                integration_config_id=integration_config_id,
            )
            if attempt >= MAX_RETRIES:
                break
            time.sleep(0.5 * attempt)
        except httpx.HTTPError as exc:
            last_error = exc
            emit_integration_event(
                "integration.external_request.failed",
                provider=provider,
                operation=operation,
                http_method=method,
                sanitized_host=host,
                endpoint_path_template=path_template,
                elapsed_ms=timed.elapsed_ms(),
                attempt=attempt,
                page_number=page_number,
                error_category="network_or_tls_failure",
                sanitized_external_error=redact_secrets(str(exc)),
                integration_config_id=integration_config_id,
            )
            break
    raise AppError(
        code="integration_unreachable",
        message="Remote integration is unreachable",
        status_code=502,
        details={
            "error": redact_secrets(str(last_error) if last_error else "unknown"),
            "error_category": "network_or_tls_failure",
            "provider": provider,
            "operation": operation,
        },
    )


def with_client(
    base_url: str,
    headers: dict[str, str],
    fn: Callable[[httpx.Client], T],
    *,
    timeout: httpx.Timeout | None = None,
) -> T:
    # httpx honors HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY by default (trust_env=True).
    verify = True
    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca_bundle:
        verify = ca_bundle
    with httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=timeout or integration_timeout(),
        follow_redirects=False,
        trust_env=True,
        verify=verify,
    ) as client:
        return fn(client)
