from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def error_body(
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }
    if request_id:
        body["request_id"] = request_id
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Request failed"
        details = detail if isinstance(detail, dict) else {}
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                code=f"http_{exc.status_code}",
                message=message,
                request_id=request_id,
                details=details if isinstance(details, dict) else {},
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Pydantic may attach exception instances under "ctx"; keep JSON-safe.
        safe_errors: list[dict[str, Any]] = []
        for item in exc.errors():
            cleaned = {
                key: (
                    str(value)
                    if not isinstance(value, (str, int, float, bool, type(None), list, dict))
                    else value
                )
                for key, value in item.items()
                if key != "ctx"
            }
            if "ctx" in item and isinstance(item["ctx"], dict):
                cleaned["ctx"] = {k: str(v) for k, v in item["ctx"].items()}
            safe_errors.append(cleaned)
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="validation_error",
                message="Request validation failed",
                request_id=request_id,
                details={"errors": safe_errors},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=500,
            content=error_body(
                code="internal_error",
                message="An unexpected error occurred",
                request_id=request_id,
            ),
        )
