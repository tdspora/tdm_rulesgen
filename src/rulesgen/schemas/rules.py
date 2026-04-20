from __future__ import annotations

from typing import Any

from pydantic import Field

from rulesgen.domain.models import DiagnosticLevel, HelperPhase, RuleIntent, SourceType
from rulesgen.schemas.common import StrictModel


class DiagnosticSchema(StrictModel):
    level: DiagnosticLevel
    code: str
    message: str
    location: str | None = None


class PromptAuditSchema(StrictModel):
    audit_id: str
    template_version: str
    backend: str
    prompt_hash: str
    suspicious: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExplainabilityTraceSchema(StrictModel):
    source_type: SourceType
    source_text: str
    semantic_frame: dict[str, Any]
    dsl_candidate: str | None = None
    normalized_expression: str | None = None
    prompt_audit_id: str | None = None
    prompt_template_version: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AggregateHelperSchema(StrictModel):
    helper_name: str
    key_expression: str
    value_expression: str | None = None


class ParseRuleRequest(StrictModel):
    source_text: str
    source_type: SourceType = SourceType.DSL
    target_column: str | None = None
    schema_columns: list[str] = Field(default_factory=list)


class ParseRuleResponse(StrictModel):
    source_type: SourceType
    intent: RuleIntent
    source_text: str
    target_column: str | None
    dependencies: list[str]
    functions: list[str]
    entities: dict[str, Any]
    diagnostics: list[DiagnosticSchema]
    dsl_candidate: str | None = None
    translation_confidence: float | None = None
    explainability_trace: ExplainabilityTraceSchema | None = None
    prompt_audit: PromptAuditSchema | None = None


class CompileRuleRequest(StrictModel):
    expression: str
    target_column: str | None = None


class CompileRuleResponse(StrictModel):
    artifact_id: str
    target_column: str | None
    expression: str
    normalized_expression: str
    dependencies: list[str]
    functions: list[str]
    helper_phases: dict[str, HelperPhase]
    aggregate_helper: AggregateHelperSchema | None = None
    dsl_version: str
    source_type: SourceType
    explainability_trace: ExplainabilityTraceSchema | None = None


class ExecuteRuleRequest(StrictModel):
    artifact_id: str | None = None
    expression: str | None = None
    target_column: str | None = None
    row: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0
    references: dict[str, list[Any]] = Field(default_factory=dict)


class ExecuteRuleResponse(StrictModel):
    artifact_id: str
    normalized_expression: str
    value: Any
    seed: int
    row: dict[str, Any] = Field(default_factory=dict)
    references: dict[str, list[Any]] = Field(default_factory=dict)
    diagnostics: list[DiagnosticSchema] = Field(default_factory=list)
    execution_mode: str = "local_preview"
