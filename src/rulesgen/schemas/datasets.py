from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from rulesgen.domain.models import ColumnSource, JobStatus
from rulesgen.domain.uploads import DatasetInputFormat
from rulesgen.schemas.common import StrictModel
from rulesgen.schemas.rules import (
    DiagnosticSchema,
    LLMRequestMetricsSchema,
    RequestSourceTypeSchema,
    SchemaColumnDefinitionSchema,
)


class RuleDraftSchema(StrictModel):
    target_column: str
    source_type: RequestSourceTypeSchema = RequestSourceTypeSchema.DSL
    source_text: str | None = None
    expression: str | None = None
    artifact_id: str | None = None


class GenerateDatasetRequest(StrictModel):
    row_count: int | None = None
    rules: list[RuleDraftSchema] = Field(default_factory=list)
    table_name: str | None = None
    schema_: list[SchemaColumnDefinitionSchema] = Field(
        default_factory=list,
        alias="schema",
        serialization_alias="schema",
    )
    schema_columns: list[str] = Field(default_factory=list)
    base_rows: list[dict[str, Any]] = Field(default_factory=list)
    file_id: str | None = None
    references: dict[str, list[Any]] = Field(default_factory=dict)
    seed: int = 0

    @model_validator(mode="after")
    def validate_request(self) -> GenerateDatasetRequest:
        embedded_targets = {item.name for item in self.schema_ if item.has_rule_definition()}
        explicit_targets = {item.target_column for item in self.rules}
        duplicate_targets = sorted(embedded_targets & explicit_targets)
        if duplicate_targets:
            raise ValueError(
                "Rule definitions cannot be duplicated between schema rows and rules: "
                + ", ".join(duplicate_targets)
            )
        has_base_rows = bool(self.base_rows)
        has_file_id = self.file_id is not None
        if has_base_rows == has_file_id:
            raise ValueError("Exactly one of base_rows or file_id must be provided.")
        if has_base_rows:
            if self.row_count is None:
                raise ValueError("row_count is required when base_rows are provided.")
            if self.row_count != len(self.base_rows):
                raise ValueError(
                    "row_count must match the number of provided base_rows for "
                    "single-table generation."
                )
            if self.row_count < 1:
                raise ValueError("row_count must be at least 1.")
        if has_file_id and self.row_count is not None:
            raise ValueError("row_count must not be provided when file_id is used.")
        return self


class DatasetUploadResponse(StrictModel):
    file_id: str
    filename: str
    media_type: str
    format: DatasetInputFormat
    row_count: int
    columns: list[str] = Field(default_factory=list)


class GenerateDatasetResponse(StrictModel):
    job_id: str
    status: JobStatus
    row_count: int
    planned_column_sources: dict[str, ColumnSource] = Field(default_factory=dict)
    diagnostics: list[DiagnosticSchema] = Field(default_factory=list)
    llm_metrics: LLMRequestMetricsSchema | None = None
