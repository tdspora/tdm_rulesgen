from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from rulesgen.api.dependencies import get_current_principal, get_jobs_service
from rulesgen.api.model_mapping import (
    to_domain_rule_drafts,
    to_domain_rule_drafts_from_schema,
    to_domain_schema,
    to_llm_metrics_schema,
)
from rulesgen.auth.models import Principal
from rulesgen.domain.models import JobKind
from rulesgen.schemas.datasets import GenerateDatasetRequest, GenerateDatasetResponse
from rulesgen.schemas.rules import DiagnosticSchema
from rulesgen.services.jobs_service import JobsService

router = APIRouter(prefix="/datasets", tags=["datasets"])


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
        rules=to_domain_rule_drafts(payload.rules)
        + to_domain_rule_drafts_from_schema(payload.schema_),
    )

    planned_column_sources = {}
    if job.result and isinstance(job.result.get("planned_column_sources"), dict):
        planned_column_sources = job.result["planned_column_sources"]

    return GenerateDatasetResponse(
        job_id=job.job_id,
        status=job.status,
        row_count=int(
            job.result.get("row_count", payload.row_count) if job.result else payload.row_count
        ),
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
