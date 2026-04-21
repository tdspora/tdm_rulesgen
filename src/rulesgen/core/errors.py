from __future__ import annotations

from typing import TYPE_CHECKING

from rulesgen.errors import (
    AppError,
    DSLParseFailed,
    DSLValidationFailed,
    Forbidden,
    NotFound,
    Unauthorized,
    ValidationFailed,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


def install_exception_handlers(app: FastAPI) -> None:
    from rulesgen.api.exception_handlers import (
        install_exception_handlers as _install_exception_handlers,
    )

    _install_exception_handlers(app)


__all__ = [
    "AppError",
    "DSLParseFailed",
    "DSLValidationFailed",
    "Forbidden",
    "NotFound",
    "Unauthorized",
    "ValidationFailed",
    "install_exception_handlers",
]
