from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from rulesgen.api.problem_details import problem_response
from rulesgen.domain.exceptions import JobNotFoundError, RuleNotFoundError
from rulesgen.errors import AppError


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
