from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from rulesgen.api.router import api_router
from rulesgen.core.config import Settings, get_settings
from rulesgen.core.errors import install_exception_handlers
from rulesgen.core.lifespan import lifespan
from rulesgen.core.logging import configure_logging
from rulesgen.middleware.exception_mapping import ExceptionMappingMiddleware
from rulesgen.middleware.request_context import RequestContextMiddleware


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    configure_logging(settings.log_level)

    middleware = [
        Middleware(ExceptionMappingMiddleware),
        Middleware(RequestContextMiddleware),
        Middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts or ["*"]),
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        ),
    ]

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        middleware=middleware,
        lifespan=lifespan,
    )
    app.state.settings = settings

    install_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
