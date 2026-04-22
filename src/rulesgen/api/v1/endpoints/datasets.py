from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from rulesgen.api.dependencies import (
    get_current_principal,
    get_dataset_upload_service,
    get_jobs_service,
)
from rulesgen.api.model_mapping import (
    to_domain_rule_drafts,
    to_domain_rule_drafts_from_schema,
    to_domain_schema,
    to_llm_metrics_schema,
)
from rulesgen.auth.models import Principal
from rulesgen.domain.models import JobKind
from rulesgen.schemas.datasets import (
    DatasetUploadResponse,
    GenerateDatasetRequest,
    GenerateDatasetResponse,
)
from rulesgen.schemas.rules import DiagnosticSchema
from rulesgen.services.dataset_upload_service import DatasetUploadService
from rulesgen.services.jobs_service import JobsService

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/uploads", response_model=DatasetUploadResponse)
async def upload_dataset(
    file: Annotated[UploadFile, File(...)],
    dataset_upload_service: Annotated[DatasetUploadService, Depends(get_dataset_upload_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> DatasetUploadResponse:
    del principal
    record = dataset_upload_service.store_upload(
        filename=file.filename,
        media_type=file.content_type,
        payload=await file.read(),
    )
    return DatasetUploadResponse(
        file_id=record.file_id,
        filename=record.filename,
        media_type=record.media_type,
        format=record.format,
        row_count=record.row_count,
        columns=record.columns,
    )


@router.post("/generate", response_model=GenerateDatasetResponse)
def generate_dataset(
    payload: GenerateDatasetRequest,
    jobs_service: Annotated[JobsService, Depends(get_jobs_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> GenerateDatasetResponse:
    del principal
    job = jobs_service.create_job(
        kind=JobKind.GENERATE_DATASET,
        artifact_id=None,
        expression=None,
        target_column=None,
        row={},
        seed=payload.seed,
        references=payload.references,
        table_name=payload.table_name,
        schema=to_domain_schema(payload.schema_),
        schema_columns=payload.schema_columns,
        row_count=payload.row_count,
        base_rows=payload.base_rows,
        file_id=payload.file_id,
        rules=to_domain_rule_drafts(payload.rules)
        + to_domain_rule_drafts_from_schema(payload.schema_),
    )

    planned_column_sources = {}
    if job.result and isinstance(job.result.get("planned_column_sources"), dict):
        planned_column_sources = job.result["planned_column_sources"]
    payload_input_source = job.payload.get("input_source", {})
    response_row_count = (
        job.result.get("row_count")
        if job.result is not None
        else payload_input_source.get("row_count", payload.row_count)
    )
    if response_row_count is None:
        raise ValueError("Dataset generation response was missing row_count metadata.")

    return GenerateDatasetResponse(
        job_id=job.job_id,
        status=job.status,
        row_count=int(response_row_count),
        planned_column_sources=planned_column_sources,
        diagnostics=[
            DiagnosticSchema(
                level=item.level,
                code=item.code,
                message=item.message,
                location=item.location,
            )
            for item in job.diagnostics
        ],
        llm_metrics=to_llm_metrics_schema(job.llm_metrics),
    )
