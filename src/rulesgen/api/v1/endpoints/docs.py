from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["docs"])


def _ensure_docs_enabled(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.docs_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.get("/v1/openapi.json", include_in_schema=False, name="v1_openapi")
def v1_openapi(request: Request) -> dict[str, Any]:
    _ensure_docs_enabled(request)

    # Imported lazily to avoid a circular import at module load time: the v1
    # router depends on this module to register the docs endpoints.
    from rulesgen.api.v1.router import router as v1_router

    app = request.app
    return get_openapi(
        title=f"{app.title} v1",
        version=app.version,
        routes=v1_router.routes,
    )


@router.get(
    "/v1/docs",
    include_in_schema=False,
    response_class=HTMLResponse,
    name="v1_docs",
)
def v1_docs(request: Request) -> HTMLResponse:
    _ensure_docs_enabled(request)
    return get_swagger_ui_html(
        openapi_url=request.app.url_path_for("v1_openapi"),
        title=f"{request.app.title} v1 - Swagger UI",
    )
