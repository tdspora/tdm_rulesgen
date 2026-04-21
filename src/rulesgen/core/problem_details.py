from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import JSONResponse


def build_problem_details(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from rulesgen.api.problem_details import build_problem_details as _build_problem_details

    return _build_problem_details(
        request,
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        errors=errors,
    )


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    from rulesgen.api.problem_details import problem_response as _problem_response

    return _problem_response(
        request,
        status_code=status_code,
        code=code,
        title=title,
        detail=detail,
        errors=errors,
    )
