from __future__ import annotations

from typing import Any

from rulesgen.container import build_compiler
from rulesgen.core.config import Settings
from rulesgen.domain.models import (
    CompiledRule,
    ExecutionPreview,
    ExplainabilityTrace,
    SchemaColumnDefinition,
    SemanticFrame,
    SourceType,
)
from rulesgen.execution.local import LocalExecutionAdapter
from rulesgen.infra.llm_gateway import LLMGatewayClient


def parse_rule(
    source_text: str,
    *,
    source_type: SourceType,
    schema_columns: list[str] | None = None,
    target_column: str | None = None,
    table_name: str | None = None,
    schema: list[SchemaColumnDefinition] | None = None,
    settings: Settings | None = None,
    gateway_client: LLMGatewayClient | None = None,
) -> SemanticFrame:
    compiler = build_compiler(settings, gateway_client=gateway_client)
    return compiler.parse(
        source_text=source_text,
        source_type=source_type,
        target_column=target_column,
        schema_columns=schema_columns or [],
        table_name=table_name,
        schema=schema,
    )


def compile_rule(
    expression: str,
    *,
    target_column: str | None = None,
    settings: Settings | None = None,
    gateway_client: LLMGatewayClient | None = None,
    source_type: SourceType = SourceType.DSL,
    explainability_trace: ExplainabilityTrace | None = None,
) -> CompiledRule:
    compiler = build_compiler(settings, gateway_client=gateway_client)
    return compiler.compile(
        expression=expression,
        target_column=target_column,
        source_type=source_type,
        explainability_trace=explainability_trace,
    )


def preview_rule(
    compiled_rule: CompiledRule,
    *,
    row: dict[str, Any] | None = None,
    seed: int = 0,
    references: dict[str, list[Any]] | None = None,
) -> ExecutionPreview:
    return LocalExecutionAdapter().execute(
        compiled_rule,
        row=row,
        seed=seed,
        references=references,
    )


__all__ = [
    "build_compiler",
    "compile_rule",
    "parse_rule",
    "preview_rule",
]
