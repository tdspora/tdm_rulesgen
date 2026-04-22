from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from rulesgen.api.dependencies import (
    get_artifact_download_service,
    get_current_principal,
    get_jobs_service,
)
from rulesgen.api.model_mapping import (
    to_domain_rule_drafts,
    to_domain_rule_drafts_from_schema,
    to_domain_schema,
    to_llm_metrics_schema,
)
from rulesgen.auth.models import Principal
from rulesgen.domain.models import JobRecord
from rulesgen.schemas.jobs import CreateJobRequest, JobArtifactSchema, JobResponse
from rulesgen.schemas.rules import DiagnosticSchema
from rulesgen.services.artifact_download_service import ArtifactDownloadService
from rulesgen.services.jobs_service import JobsService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_job_response(job: JobRecord) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        kind=job.kind,
        status=job.status,
        payload=job.payload,
        result=job.result,
        error=job.error,
        diagnostics=[
            DiagnosticSchema(
                level=item.level,
                code=item.code,
                message=item.message,
                location=item.location,
            )
            for item in job.diagnostics
        ],
        artifacts=[
            JobArtifactSchema(
                artifact_id=item.artifact_id,
                kind=item.kind,
                path=item.path,
                media_type=item.media_type,
                metadata=item.metadata,
            )
            for item in job.artifacts
        ],
        llm_metrics=to_llm_metrics_schema(job.llm_metrics),
    )


@router.post("", response_model=JobResponse)
def create_job(
    payload: CreateJobRequest,
    jobs_service: Annotated[JobsService, Depends(get_jobs_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> JobResponse:
    del principal
    job = jobs_service.create_job(
        kind=payload.kind,
        artifact_id=payload.artifact_id,
        expression=payload.expression,
        target_column=payload.target_column,
        row=payload.row,
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
    return _to_job_response(job)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    jobs_service: Annotated[JobsService, Depends(get_jobs_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> JobResponse:
    del principal
    job = jobs_service.get_job(job_id)
    return _to_job_response(job)


@router.get("/{job_id}/dataset", response_class=FileResponse)
def download_job_dataset(
    job_id: str,
    artifact_download_service: Annotated[
        ArtifactDownloadService, Depends(get_artifact_download_service)
    ],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> FileResponse:
    del principal
    download = artifact_download_service.resolve_dataset(job_id)
    return FileResponse(
        path=download.source_path,
        media_type=download.media_type,
        filename=download.filename,
        content_disposition_type="attachment",
    )


@router.get("/{job_id}/artifacts/{artifact_id}", response_class=FileResponse)
def download_job_artifact(
    job_id: str,
    artifact_id: str,
    artifact_download_service: Annotated[
        ArtifactDownloadService, Depends(get_artifact_download_service)
    ],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> FileResponse:
    del principal
    download = artifact_download_service.resolve_artifact(job_id, artifact_id)
    return FileResponse(
        path=download.source_path,
        media_type=download.media_type,
        filename=download.filename,
        content_disposition_type="attachment",
    )
