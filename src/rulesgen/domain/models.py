from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import CodeType
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceType(StrEnum):
    DSL = "dsl"
    NATURAL_LANGUAGE = "natural_language"


class SchemaColumnSource(StrEnum):
    SYNGEN = "syngen"
    RULE = "rule"
    BASE = "base"


class DiagnosticLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RuleIntent(StrEnum):
    DSL_EXPRESSION = "dsl_expression"
    ARITHMETIC = "arithmetic"
    CONDITIONAL = "conditional"
    FAKER = "faker"
    PATTERN = "pattern"
    FOREIGN_KEY = "foreign_key"
    AGGREGATE = "aggregate"
    UNKNOWN = "unknown"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HelperPhase(StrEnum):
    ROW = "row"
    GROUP = "group"


class JobKind(StrEnum):
    EXECUTE_PREVIEW = "execute_preview"
    COMPILE_PREVIEW = "compile_preview"
    SANDBOX_EXECUTE = "sandbox_execute"
    GENERATE_DATASET = "generate_dataset"


class ArtifactKind(StrEnum):
    INPUT_MANIFEST = "input_manifest"
    DATASET = "dataset"
    EXECUTION_LOG = "execution_log"
    DIAGNOSTICS = "diagnostics"
    COMPILED_RULE = "compiled_rule"


class ColumnSource(StrEnum):
    MODEL_GENERATED = "model_generated"
    RULE_GENERATED = "rule_generated"
    HYBRID = "hybrid"


@dataclass(slots=True)
class Diagnostic:
    level: DiagnosticLevel
    code: str
    message: str
    location: str | None = None


@dataclass(slots=True)
class SchemaColumnDefinition:
    name: str
    data_type: str
    nullable: bool
    source: SchemaColumnSource
    notes: str | None = None


@dataclass(slots=True)
class NaturalLanguageRuleRequest:
    target_column: str
    source_text: str


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CostBreakdown:
    total_cost: float | None = None
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CacheInsight:
    backend: str | None = None
    enabled: bool = False
    hit: bool = False
    scope_key: str | None = None
    similarity: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMRequestMetrics:
    usage: TokenUsage | None = None
    cost: CostBreakdown | None = None
    latency_ms: float | None = None
    attempts: int = 1
    cache: CacheInsight | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptAuditRecord:
    audit_id: str
    template_version: str
    backend: str
    prompt_text: str
    prompt_hash: str
    response_text: str | None = None
    suspicious: bool = False
    prompt_kind: str = "initial"
    attempt_number: int = 1
    model_name: str | None = None
    provider_name: str | None = None
    latency_ms: float | None = None
    metrics: LLMRequestMetrics | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ExplainabilityTrace:
    source_type: SourceType
    source_text: str
    semantic_frame: dict[str, Any]
    dsl_candidate: str | None
    normalized_expression: str | None = None
    prompt_audit_id: str | None = None
    prompt_audit_ids: list[str] = field(default_factory=list)
    prompt_template_version: str | None = None
    model_name: str | None = None
    provider_name: str | None = None
    metrics: LLMRequestMetrics | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AggregateHelperSpec:
    helper_name: str
    key_expression: str
    value_expression: str | None = None


@dataclass(slots=True)
class SemanticFrame:
    source_type: SourceType
    intent: RuleIntent
    source_text: str
    target_column: str | None
    dependencies: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    dsl_candidate: str | None = None
    translation_confidence: float | None = None
    explainability_trace: ExplainabilityTrace | None = None
    prompt_audit: PromptAuditRecord | None = None
    prompt_audits: list[PromptAuditRecord] = field(default_factory=list)
    metrics: LLMRequestMetrics | None = None


@dataclass(slots=True)
class BatchTranslationItem:
    target_column: str | None
    dsl_candidate: str | None = None
    explanation: str | None = None
    error: str | None = None
    reason: str | None = None
    suggestion: str | None = None
    intent: RuleIntent = RuleIntent.UNKNOWN
    entities: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    confidence: float | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.dsl_candidate is not None


@dataclass(slots=True)
class GatewayTranslationBatch:
    items: list[BatchTranslationItem]
    prompt_audits: list[PromptAuditRecord] = field(default_factory=list)
    backend: str = "stub"
    provider_name: str | None = None
    model_name: str | None = None
    metrics: LLMRequestMetrics | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SemanticFrameBatch:
    frames: list[SemanticFrame]
    prompt_audits: list[PromptAuditRecord] = field(default_factory=list)
    metrics: LLMRequestMetrics | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompiledRule:
    artifact_id: str
    target_column: str | None
    expression: str
    normalized_expression: str
    dependencies: list[str]
    functions: list[str]
    helper_phases: dict[str, HelperPhase]
    aggregate_helper: AggregateHelperSpec | None
    source_type: SourceType
    code_object: CodeType
    dsl_version: str = "v1"
    explainability_trace: ExplainabilityTrace | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ExecutionPreview:
    value: Any
    row: dict[str, Any]
    seed: int
    references: dict[str, list[Any]] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(slots=True)
class GeneratedArtifact:
    artifact_id: str
    job_id: str
    kind: ArtifactKind
    path: str
    media_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class SandboxExecutionResult:
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    output_path: str | None = None
    row_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    kind: JobKind
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifacts: list[GeneratedArtifact] = field(default_factory=list)
    llm_metrics: LLMRequestMetrics | None = None
