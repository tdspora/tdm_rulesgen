from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rulesgen.domain.models import (
    ColumnSource,
    CompiledRule,
    LLMRequestMetrics,
    SchemaColumnDefinition,
    SourceType,
)


@dataclass(slots=True)
class RuleDraft:
    target_column: str
    source_type: SourceType = SourceType.DSL
    source_text: str | None = None
    expression: str | None = None
    artifact_id: str | None = None


@dataclass(slots=True)
class DatasetGenerationRequest:
    row_count: int
    rules: list[RuleDraft]
    table_name: str | None = None
    schema: list[SchemaColumnDefinition] = field(default_factory=list)
    schema_columns: list[str] = field(default_factory=list)
    base_rows: list[dict[str, Any]] = field(default_factory=list)
    references: dict[str, list[Any]] = field(default_factory=dict)
    seed: int = 0


@dataclass(slots=True)
class PlannedRule:
    target_column: str
    compiled_rule: CompiledRule
    source: ColumnSource


@dataclass(slots=True)
class DatasetGenerationPlan:
    row_count: int
    table_name: str | None
    schema: list[SchemaColumnDefinition]
    schema_columns: list[str]
    planned_rules: list[PlannedRule]
    column_sources: dict[str, ColumnSource]
    seed: int
    llm_metrics: LLMRequestMetrics | None = None
