"""Rulesgen library and optional FastAPI application."""

from rulesgen.container import AppContainer, build_compiler, build_container, build_gateway_client
from rulesgen.core.config import Settings
from rulesgen.domain.models import CompiledRule, ExecutionPreview, SemanticFrame, SourceType
from rulesgen.errors import (
    AppError,
    DSLParseFailed,
    DSLValidationFailed,
    Forbidden,
    NotFound,
    Unauthorized,
    ValidationFailed,
)
from rulesgen.execution.engine import GenerationRun, execute_generation_plan, execute_preview_rule
from rulesgen.library import compile_rule, parse_rule, preview_rule
from rulesgen.version_info import package_version

__all__ = [
    "__version__",
    "AppContainer",
    "AppError",
    "CompiledRule",
    "DSLParseFailed",
    "DSLValidationFailed",
    "ExecutionPreview",
    "Forbidden",
    "GenerationRun",
    "NotFound",
    "SemanticFrame",
    "Settings",
    "SourceType",
    "Unauthorized",
    "ValidationFailed",
    "build_compiler",
    "build_container",
    "build_gateway_client",
    "compile_rule",
    "execute_generation_plan",
    "execute_preview_rule",
    "parse_rule",
    "preview_rule",
]

__version__ = package_version()
