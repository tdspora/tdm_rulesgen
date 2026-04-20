from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from rulesgen.api.dependencies import get_current_principal, get_jobs_service
from rulesgen.auth.models import Principal
from rulesgen.domain.generation import RuleDraft
from rulesgen.domain.models import JobRecord
from rulesgen.schemas.jobs import CreateJobRequest, JobArtifactSchema, JobResponse
from rulesgen.schemas.rules import DiagnosticSchema
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
        schema_columns=payload.schema_columns,
        row_count=payload.row_count,
        base_rows=payload.base_rows,
        rules=[
            RuleDraft(
                target_column=item.target_column,
                source_type=item.source_type,
                source_text=item.source_text,
                expression=item.expression,
                artifact_id=item.artifact_id,
            )
            for item in payload.rules
        ],
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
