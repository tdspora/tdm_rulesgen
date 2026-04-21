from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from rulesgen.domain.models import (
    DiagnosticLevel,
    HelperPhase,
    RuleIntent,
    SchemaColumnSource,
    SourceType,
)
from rulesgen.schemas.common import StrictModel


class RequestSourceTypeSchema(StrEnum):
    NATURAL_LANGUAGE = "natural_language"
    DOMAIN_SPECIFIC_LANGUAGE = "domain_specific_language"
    DSL = "dsl"


class DiagnosticSchema(StrictModel):
    level: DiagnosticLevel
    code: str
    message: str
    location: str | None = None


class SchemaColumnDefinitionSchema(StrictModel):
    name: str
    type: str
    nullable: bool
    source: SchemaColumnSource
    notes: str | None = None
    source_text: str | None = None
    source_type: RequestSourceTypeSchema | None = None
    artifact_id: str | None = None

    @model_validator(mode="after")
    def validate_embedded_rule(self) -> SchemaColumnDefinitionSchema:
        if not self.has_rule_definition():
            return self
        if self.artifact_id is not None and self.source_text is None and self.source_type is None:
            return self
        if self.source_text is None or self.source_type is None:
            raise ValueError(
                "Schema rows with embedded rules must provide both source_text and source_type."
            )
        return self

    def has_rule_definition(self) -> bool:
        return (
            self.source_text is not None
            or self.source_type is not None
            or self.artifact_id is not None
        )


class TokenUsageSchema(StrictModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CostBreakdownSchema(StrictModel):
    total_cost: float | None = None
    currency: str = "USD"
    raw: dict[str, Any] = Field(default_factory=dict)


class CacheInsightSchema(StrictModel):
    backend: str | None = None
    enabled: bool = False
    hit: bool = False
    scope_key: str | None = None
    similarity: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMRequestMetricsSchema(StrictModel):
    usage: TokenUsageSchema | None = None
    cost: CostBreakdownSchema | None = None
    latency_ms: float | None = None
    attempts: int = 1
    cache: CacheInsightSchema | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptAuditSchema(StrictModel):
    audit_id: str
    template_version: str
    backend: str
    prompt_hash: str
    suspicious: bool = False
    prompt_kind: str = "initial"
    attempt_number: int = 1
    model_name: str | None = None
    provider_name: str | None = None
    latency_ms: float | None = None
    metrics: LLMRequestMetricsSchema | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExplainabilityTraceSchema(StrictModel):
    source_type: SourceType
    source_text: str
    semantic_frame: dict[str, Any]
    dsl_candidate: str | None = None
    normalized_expression: str | None = None
    prompt_audit_id: str | None = None
    prompt_audit_ids: list[str] = Field(default_factory=list)
    prompt_template_version: str | None = None
    model_name: str | None = None
    provider_name: str | None = None
    metrics: LLMRequestMetricsSchema | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AggregateHelperSchema(StrictModel):
    helper_name: str
    key_expression: str
    value_expression: str | None = None


class ParseRuleRequest(StrictModel):
    source_text: str | None = None
    source_type: RequestSourceTypeSchema | None = None
    target_column: str | None = None
    table_name: str | None = None
    schema_: list[SchemaColumnDefinitionSchema] = Field(
        default_factory=list,
        alias="schema",
        serialization_alias="schema",
    )
    schema_columns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_request_shape(self) -> ParseRuleRequest:
        embedded_rule_columns = [item for item in self.schema_ if item.has_rule_definition()]
        uses_top_level_fields = any(
            value is not None for value in (self.source_text, self.source_type, self.target_column)
        )

        if embedded_rule_columns:
            if uses_top_level_fields:
                raise ValueError(
                    "Use either top-level source_text/source_type/target_column or "
                    "an embedded schema rule definition, not both."
                )
            if len(embedded_rule_columns) != 1:
                raise ValueError(
                    "rules/parse requires exactly one schema row with source_text/source_type."
                )
            embedded_rule = embedded_rule_columns[0]
            if embedded_rule.artifact_id is not None and embedded_rule.source_text is None:
                raise ValueError("rules/parse does not support artifact_id-only schema rows.")
            return self

        if self.source_text is None or self.source_type is None:
            raise ValueError(
                "rules/parse requires source_text and source_type, or one embedded schema rule."
            )
        if (
            self.source_type is RequestSourceTypeSchema.NATURAL_LANGUAGE
            and self.target_column is None
        ):
            raise ValueError(
                "Natural-language parsing requires target_column unless the rule is embedded "
                "on a schema row."
            )
        return self


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
    prompt_audits: list[PromptAuditSchema] = Field(default_factory=list)
    metrics: LLMRequestMetricsSchema | None = None


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
