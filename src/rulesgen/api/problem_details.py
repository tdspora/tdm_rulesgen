from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from rulesgen.core.config import get_settings


def build_problem_details(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    body: dict[str, Any] = {
        "type": f"{settings.problem_base_url.rstrip('/')}/{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }
    if errors:
        body["errors"] = errors
    return body


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_problem_details(
            request,
            status_code=status_code,
            code=code,
            title=title,
            detail=detail,
            errors=errors,
        ),
        media_type="application/problem+json",
    )
