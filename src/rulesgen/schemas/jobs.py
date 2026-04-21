from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from rulesgen.domain.models import ArtifactKind, JobKind, JobStatus
from rulesgen.schemas.common import StrictModel
from rulesgen.schemas.rules import (
    DiagnosticSchema,
    LLMRequestMetricsSchema,
    RequestSourceTypeSchema,
    SchemaColumnDefinitionSchema,
)


class JobArtifactSchema(StrictModel):
    artifact_id: str
    kind: ArtifactKind
    path: str
    media_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRuleDraftSchema(StrictModel):
    target_column: str
    source_type: RequestSourceTypeSchema = RequestSourceTypeSchema.DSL
    source_text: str | None = None
    expression: str | None = None
    artifact_id: str | None = None


class CreateJobRequest(StrictModel):
    kind: JobKind = JobKind.EXECUTE_PREVIEW
    artifact_id: str | None = None
    expression: str | None = None
    target_column: str | None = None
    row: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0
    references: dict[str, list[Any]] = Field(default_factory=dict)
    table_name: str | None = None
    schema_: list[SchemaColumnDefinitionSchema] = Field(
        default_factory=list,
        alias="schema",
        serialization_alias="schema",
    )
    schema_columns: list[str] = Field(default_factory=list)
    row_count: int | None = None
    base_rows: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[JobRuleDraftSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rule_targets(self) -> CreateJobRequest:
        embedded_targets = {
            item.name for item in self.schema_ if item.has_rule_definition()
        }
        explicit_targets = {item.target_column for item in self.rules}
        duplicate_targets = sorted(embedded_targets & explicit_targets)
        if duplicate_targets:
            raise ValueError(
                "Rule definitions cannot be duplicated between schema rows and rules: "
                + ", ".join(duplicate_targets)
            )
        return self


class JobResponse(StrictModel):
    job_id: str
    kind: JobKind
    status: JobStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    diagnostics: list[DiagnosticSchema] = Field(default_factory=list)
    artifacts: list[JobArtifactSchema] = Field(default_factory=list)
    llm_metrics: LLMRequestMetricsSchema | None = None
