from __future__ import annotations

import logging
import time
import uuid
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers[self.header_name] = request_id
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request completed method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Allow same-origin microphone for workshop WebRTC voice capture; keep camera/geo blocked.
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(self), geolocation=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        if self.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    """Reject cross-site cookie-authenticated mutating API calls when Origin is present."""

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in self.SAFE_METHODS or not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Public remote token endpoints authenticate via signed invite token, not cookies.
        if request.url.path.startswith("/api/remote/"):
            return await call_next(request)

        settings = get_settings()
        cookie_name = settings.session_cookie_name
        if cookie_name not in request.cookies:
            return await call_next(request)

        origin = request.headers.get("origin")
        fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
        if fetch_site == "cross-site":
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "csrf_origin_rejected",
                        "message": "Cross-site request is not allowed",
                    }
                },
            )
        if not origin:
            # Same-origin fetch / TestClient often omit Origin; allow only when not cross-site.
            if fetch_site in {"", "same-origin", "same-site", "none"}:
                return await call_next(request)
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "csrf_origin_rejected",
                        "message": "Request origin is not allowed",
                    }
                },
            )

        allowed = set(settings.cors_origin_list)
        if settings.public_base_url:
            allowed.add(settings.public_base_url.rstrip("/"))
        parsed = urlparse(origin)
        origin_base = f"{parsed.scheme}://{parsed.netloc}"
        if origin_base not in allowed and origin not in allowed:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "csrf_origin_rejected",
                        "message": "Request origin is not allowed",
                    }
                },
            )
        return await call_next(request)
