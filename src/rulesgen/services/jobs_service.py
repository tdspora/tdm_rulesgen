from __future__ import annotations

from typing import Any
from uuid import uuid4

from rulesgen.domain.generation import DatasetGenerationRequest, RuleDraft
from rulesgen.domain.models import JobKind, JobRecord, JobStatus, SchemaColumnDefinition, utc_now
from rulesgen.domain.repositories import JobRepository
from rulesgen.domain.uploads import DatasetInputSource
from rulesgen.errors import ValidationFailed
from rulesgen.services.dataset_upload_service import DatasetUploadService
from rulesgen.services.generation_service import GenerationService
from rulesgen.services.rules_service import RulesService


class JobsService:
    def __init__(
        self,
        *,
        job_repository: JobRepository,
        rules_service: RulesService,
        generation_service: GenerationService,
        dataset_upload_service: DatasetUploadService,
    ) -> None:
        self.job_repository = job_repository
        self.rules_service = rules_service
        self.generation_service = generation_service
        self.dataset_upload_service = dataset_upload_service

    def create_job(
        self,
        *,
        kind: JobKind,
        artifact_id: str | None,
        expression: str | None,
        target_column: str | None,
        row: dict[str, Any],
        seed: int,
        references: dict[str, list[Any]],
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        schema_columns: list[str],
        row_count: int | None,
        base_rows: list[dict[str, Any]],
        file_id: str | None,
        rules: list[RuleDraft],
    ) -> JobRecord:
        created_at = utc_now()
        job_id = str(uuid4())
        input_source: DatasetInputSource | None = None
        resolved_row_count = row_count
        if kind in {JobKind.GENERATE_DATASET, JobKind.SANDBOX_EXECUTE}:
            input_source = self.dataset_upload_service.resolve_input(
                job_id=job_id,
                base_rows=base_rows,
                row_count=row_count,
                file_id=file_id,
            )
            resolved_row_count = input_source.row_count
        job = JobRecord(
            job_id=job_id,
            kind=kind,
            status=JobStatus.RUNNING,
            created_at=created_at,
            updated_at=created_at,
            payload={
                "artifact_id": artifact_id,
                "expression": expression,
                "target_column": target_column,
                "row": row,
                "seed": seed,
                "references": references,
                "table_name": table_name,
                "schema": [self._serialize_schema_column(item) for item in schema],
                "schema_columns": schema_columns,
                "row_count": resolved_row_count,
                "file_id": file_id,
                "input_source": (
                    self._serialize_input_source(input_source) if input_source is not None else None
                ),
                "rules": [
                    {
                        "target_column": item.target_column,
                        "source_type": item.source_type.value,
                        "source_text": item.source_text,
                        "expression": item.expression,
                        "artifact_id": item.artifact_id,
                    }
                    for item in rules
                ],
            },
        )
        self.job_repository.save(job)

        try:
            self._run_job(
                job=job,
                artifact_id=artifact_id,
                expression=expression,
                target_column=target_column,
                row=row,
                seed=seed,
                references=references,
                table_name=table_name,
                schema=schema,
                schema_columns=schema_columns,
                row_count=resolved_row_count,
                input_source=input_source,
                rules=rules,
            )
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED
            job.updated_at = utc_now()
            job.error = str(exc)
            return self.job_repository.update(job)

        return self.job_repository.update(job)

    def get_job(self, job_id: str) -> JobRecord:
        return self.job_repository.get(job_id)

    def _run_job(
        self,
        *,
        job: JobRecord,
        artifact_id: str | None,
        expression: str | None,
        target_column: str | None,
        row: dict[str, Any],
        seed: int,
        references: dict[str, list[Any]],
        table_name: str | None,
        schema: list[SchemaColumnDefinition],
        schema_columns: list[str],
        row_count: int | None,
        input_source: DatasetInputSource | None,
        rules: list[RuleDraft],
    ) -> None:
        if job.kind is JobKind.EXECUTE_PREVIEW:
            compiled_rule, preview = self.rules_service.execute(
                artifact_id=artifact_id,
                expression=expression,
                target_column=target_column,
                row=row,
                seed=seed,
                references=references,
            )
            job.status = JobStatus.SUCCEEDED
            job.updated_at = utc_now()
            job.result = {
                "artifact_id": compiled_rule.artifact_id,
                "normalized_expression": compiled_rule.normalized_expression,
                "value": preview.value,
                "seed": preview.seed,
            }
            job.diagnostics = preview.diagnostics
            return

        if job.kind is JobKind.COMPILE_PREVIEW:
            if expression is None:
                raise ValidationFailed("compile_preview jobs require an expression.")
            compiled_rule = self.rules_service.compile(
                expression=expression,
                target_column=target_column,
            )
            job.status = JobStatus.SUCCEEDED
            job.updated_at = utc_now()
            job.result = {
                "artifact_id": compiled_rule.artifact_id,
                "normalized_expression": compiled_rule.normalized_expression,
                "functions": compiled_rule.functions,
                "dependencies": compiled_rule.dependencies,
            }
            return

        if job.kind in {JobKind.GENERATE_DATASET, JobKind.SANDBOX_EXECUTE}:
            if input_source is None:
                raise ValidationFailed("Generation jobs require a resolved input source.")
            effective_row_count = input_source.row_count
            if effective_row_count <= 0:
                raise ValidationFailed(
                    "Generation jobs require a staged input source with row_count > 0."
                )
            request = DatasetGenerationRequest(
                row_count=effective_row_count,
                rules=rules,
                input_source=input_source,
                table_name=table_name,
                schema=schema,
                schema_columns=schema_columns,
                references=references,
                seed=seed,
            )
            plan, sandbox_result = self.generation_service.generate(
                job_id=job.job_id,
                request=request,
            )
            job.status = JobStatus.SUCCEEDED
            job.updated_at = utc_now()
            job.result = {
                "output_path": sandbox_result.output_path,
                "row_count": sandbox_result.row_count,
                "planned_column_sources": {
                    name: source.value for name, source in plan.column_sources.items()
                },
                "row_rule_order": sandbox_result.metadata.get("row_rule_order", []),
                "group_rule_order": sandbox_result.metadata.get("group_rule_order", []),
                "input_source": self._serialize_input_source(input_source),
            }
            job.diagnostics = sandbox_result.diagnostics
            job.artifacts = sandbox_result.artifacts
            job.llm_metrics = plan.llm_metrics
            return

        raise ValidationFailed(f"Unsupported job kind: {job.kind.value}")

    def _serialize_schema_column(self, item: SchemaColumnDefinition) -> dict[str, Any]:
        return {
            "name": item.name,
            "data_type": item.data_type,
            "nullable": item.nullable,
            "source": item.source.value,
            "notes": item.notes,
        }

    def _serialize_input_source(self, input_source: DatasetInputSource) -> dict[str, Any]:
        return {
            "source_id": input_source.source_id,
            "origin": input_source.origin.value,
            "filename": input_source.filename,
            "media_type": input_source.media_type,
            "format": input_source.format.value,
            "row_count": input_source.row_count,
            "columns": list(input_source.columns),
            "storage_path": input_source.storage_path,
        }
