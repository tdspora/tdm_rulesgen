from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from rulesgen.domain.models import Diagnostic


def _serialize_diagnostics(errors: list[Diagnostic] | None) -> list[dict[str, Any]] | None:
    if not errors:
        return None
    return [
        {
            "level": item.level.value,
            "code": item.code,
            "message": item.message,
            "location": item.location,
        }
        for item in errors
    ]


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
        super().__init__(
            code="dsl_parse_failed",
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            errors=_serialize_diagnostics(errors),
        )


class DSLValidationFailed(AppError):
    def __init__(self, message: str, errors: list[Diagnostic] | None = None) -> None:
        super().__init__(
            code="dsl_validation_failed",
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            errors=_serialize_diagnostics(errors),
        )


class GuardrailBlocked(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="guardrail_blocked",
            message=message,
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


__all__ = [
    "AppError",
    "DSLParseFailed",
    "DSLValidationFailed",
    "Forbidden",
    "GuardrailBlocked",
    "NotFound",
    "Unauthorized",
    "ValidationFailed",
]
