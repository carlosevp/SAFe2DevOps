from __future__ import annotations

import logging
import signal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.bootstrap import bootstrap_runtime, log_storage_diagnostics
from app.core.config import get_settings, reset_settings_cache
from app.core.db import dispose_engine, init_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import CsrfOriginMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
_shutdown_requested = False


def _handle_sigterm(signum: int, _frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("received signal %s; requesting graceful shutdown", signum)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Entrypoint already bootstraps in containers; re-run is idempotent for local uvicorn.
    settings = bootstrap_runtime(run_db_migrations=True)
    logger.info("starting app env=%s", settings.app_env)
    init_engine(settings)
    log_storage_diagnostics(settings, StorageService(settings))

    previous_handler = None
    try:
        previous_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except ValueError:
        # signal handlers can only be set in the main thread (e.g. pytest TestClient).
        logger.debug("skipping SIGTERM handler registration outside main thread")

    try:
        yield
    finally:
        logger.info("shutting down application")
        dispose_engine()
        if previous_handler is not None:
            try:
                signal.signal(signal.SIGTERM, previous_handler)
            except ValueError:
                pass


def create_app() -> FastAPI:
    reset_settings_cache()
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="SAFe DevOps Adaptive Assessment",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url="/api/redoc" if settings.app_env != "production" else None,
        openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.is_production)
    app.add_middleware(CsrfOriginMiddleware)
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    dist = Path(settings.frontend_dist)
    if dist.exists():
        # Low-priority SPA routes; `/api` path operations always win.
        app.frontend("/", directory=str(dist), fallback="index.html", check_dir=False)
        logger.info("serving frontend from packaged dist")
    else:
        logger.warning("frontend dist not found; API-only mode")

    return app


app = create_app()
