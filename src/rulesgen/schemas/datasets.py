from __future__ import annotations

from typing import Any

from pydantic import Field

from rulesgen.domain.models import ColumnSource, JobStatus, SourceType
from rulesgen.schemas.common import StrictModel
from rulesgen.schemas.rules import DiagnosticSchema


class RuleDraftSchema(StrictModel):
    target_column: str
    source_type: SourceType = SourceType.DSL
    source_text: str | None = None
    expression: str | None = None
    artifact_id: str | None = None


class GenerateDatasetRequest(StrictModel):
    row_count: int
    rules: list[RuleDraftSchema]
    schema_columns: list[str] = Field(default_factory=list)
    base_rows: list[dict[str, Any]] = Field(default_factory=list)
    references: dict[str, list[Any]] = Field(default_factory=dict)
    seed: int = 0


class GenerateDatasetResponse(StrictModel):
    job_id: str
    status: JobStatus
    row_count: int
    planned_column_sources: dict[str, ColumnSource] = Field(default_factory=dict)
    diagnostics: list[DiagnosticSchema] = Field(default_factory=list)
