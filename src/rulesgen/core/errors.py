from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from rulesgen.core.problem_details import problem_response
from rulesgen.domain.exceptions import JobNotFoundError, RuleNotFoundError
from rulesgen.domain.models import Diagnostic


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    errors: list[dict[str, Any]] | None = None


class ValidationFailed(AppError):
    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(
            code="validation_failed",
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            errors=errors,
        )


class Unauthorized(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(
            code="unauthorized",
            message=message,
            status_code=HTTPStatus.UNAUTHORIZED,
        )


class Forbidden(AppError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(
            code="forbidden",
            message=message,
            status_code=HTTPStatus.FORBIDDEN,
        )


class NotFound(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(
            code="not_found",
            message=message,
            status_code=HTTPStatus.NOT_FOUND,
        )


class DSLParseFailed(AppError):
    def __init__(self, message: str, errors: list[Diagnostic] | None = None) -> None:
        serialized = None
        if errors:
            serialized = [
                {
                    "level": item.level.value,
                    "code": item.code,
                    "message": item.message,
                    "location": item.location,
                }
                for item in errors
            ]
        super().__init__(
            code="dsl_parse_failed",
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            errors=serialized,
        )


class DSLValidationFailed(AppError):
    def __init__(self, message: str, errors: list[Diagnostic] | None = None) -> None:
        serialized = None
        if errors:
            serialized = [
                {
                    "level": item.level.value,
                    "code": item.code,
                    "message": item.message,
                    "location": item.location,
                }
                for item in errors
            ]
        super().__init__(
            code="dsl_validation_failed",
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            errors=serialized,
        )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):  # type: ignore[no-untyped-def]
        return problem_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            title=exc.code.replace("_", " ").title(),
            detail=exc.message,
            errors=exc.errors,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(  # type: ignore[no-untyped-def]
        request: Request, exc: RequestValidationError
    ):
        return problem_response(
            request,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="request_validation_failed",
            title="Request Validation Failed",
            detail="The request body or parameters were invalid.",
            errors=[
                {
                    "loc": [str(item) for item in err["loc"]],
                    "msg": err["msg"],
                    "type": err["type"],
                }
                for err in exc.errors()
            ],
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
        return problem_response(
            request,
            status_code=exc.status_code,
            code="http_error",
            title="HTTP Error",
            detail=str(exc.detail),
        )

    @app.exception_handler(RuleNotFoundError)
    async def rule_not_found_handler(request: Request, exc: RuleNotFoundError):  # type: ignore[no-untyped-def]
        return problem_response(
            request,
            status_code=HTTPStatus.NOT_FOUND,
            code="rule_not_found",
            title="Rule Not Found",
            detail=str(exc) or "Rule was not found.",
        )

    @app.exception_handler(JobNotFoundError)
    async def job_not_found_handler(request: Request, exc: JobNotFoundError):  # type: ignore[no-untyped-def]
        return problem_response(
            request,
            status_code=HTTPStatus.NOT_FOUND,
            code="job_not_found",
            title="Job Not Found",
            detail=str(exc) or "Job was not found.",
        )
