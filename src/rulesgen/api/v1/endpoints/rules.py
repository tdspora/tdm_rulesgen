from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from rulesgen.api.dependencies import get_current_principal, get_rules_service
from rulesgen.api.model_mapping import (
    to_domain_schema,
    to_llm_metrics_schema,
    to_parse_request_args,
)
from rulesgen.auth.models import Principal
from rulesgen.domain.models import (
    AggregateHelperSpec,
    Diagnostic,
    ExplainabilityTrace,
    PromptAuditRecord,
)
from rulesgen.schemas.rules import (
    AggregateHelperSchema,
    CompileRuleRequest,
    CompileRuleResponse,
    DiagnosticSchema,
    ExecuteRuleRequest,
    ExecuteRuleResponse,
    ExplainabilityTraceSchema,
    ParseRuleRequest,
    ParseRuleResponse,
    PromptAuditSchema,
)
from rulesgen.services.rules_service import RulesService

router = APIRouter(prefix="/rules", tags=["rules"])


def _to_diagnostic_schema(item: Diagnostic) -> DiagnosticSchema:
    return DiagnosticSchema(
        level=item.level,
        code=item.code,
        message=item.message,
        location=item.location,
    )


def _to_trace_schema(trace: ExplainabilityTrace | None) -> ExplainabilityTraceSchema | None:
    if trace is None:
        return None
    return ExplainabilityTraceSchema(
        source_type=trace.source_type,
        source_text=trace.source_text,
        semantic_frame=trace.semantic_frame,
        dsl_candidate=trace.dsl_candidate,
        normalized_expression=trace.normalized_expression,
        prompt_audit_id=trace.prompt_audit_id,
        prompt_audit_ids=trace.prompt_audit_ids,
        prompt_template_version=trace.prompt_template_version,
        model_name=trace.model_name,
        provider_name=trace.provider_name,
        metrics=to_llm_metrics_schema(trace.metrics),
        metadata=trace.metadata,
    )


def _to_prompt_audit_schema(record: PromptAuditRecord | None) -> PromptAuditSchema | None:
    if record is None:
        return None
    return PromptAuditSchema(
        audit_id=record.audit_id,
        template_version=record.template_version,
        backend=record.backend,
        prompt_hash=record.prompt_hash,
        suspicious=record.suspicious,
        prompt_kind=record.prompt_kind,
        attempt_number=record.attempt_number,
        model_name=record.model_name,
        provider_name=record.provider_name,
        latency_ms=record.latency_ms,
        metrics=to_llm_metrics_schema(record.metrics),
        metadata=record.metadata,
    )


def _to_aggregate_schema(spec: AggregateHelperSpec | None) -> AggregateHelperSchema | None:
    if spec is None:
        return None
    return AggregateHelperSchema(
        helper_name=spec.helper_name,
        key_expression=spec.key_expression,
        value_expression=spec.value_expression,
    )


@router.post("/parse", response_model=ParseRuleResponse)
def parse_rule(
    payload: ParseRuleRequest,
    rules_service: Annotated[RulesService, Depends(get_rules_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ParseRuleResponse:
    del principal
    source_text, source_type, target_column = to_parse_request_args(payload)
    frame = rules_service.parse(
        source_text=source_text,
        source_type=source_type,
        target_column=target_column,
        table_name=payload.table_name,
        schema=to_domain_schema(payload.schema_),
        schema_columns=payload.schema_columns,
    )
    return ParseRuleResponse(
        source_type=frame.source_type,
        intent=frame.intent,
        source_text=frame.source_text,
        target_column=frame.target_column,
        dependencies=frame.dependencies,
        functions=frame.functions,
        entities=frame.entities,
        diagnostics=[_to_diagnostic_schema(item) for item in frame.diagnostics],
        dsl_candidate=frame.dsl_candidate,
        translation_confidence=frame.translation_confidence,
        explainability_trace=_to_trace_schema(frame.explainability_trace),
        prompt_audit=_to_prompt_audit_schema(frame.prompt_audit),
        prompt_audits=[
            _to_prompt_audit_schema(item)
            for item in frame.prompt_audits
            if item is not None
        ],
        metrics=to_llm_metrics_schema(frame.metrics),
    )


@router.post("/compile", response_model=CompileRuleResponse)
def compile_rule(
    payload: CompileRuleRequest,
    rules_service: Annotated[RulesService, Depends(get_rules_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> CompileRuleResponse:
    del principal
    compiled_rule = rules_service.compile(
        expression=payload.expression,
        target_column=payload.target_column,
    )
    return CompileRuleResponse(
        artifact_id=compiled_rule.artifact_id,
        target_column=compiled_rule.target_column,
        expression=compiled_rule.expression,
        normalized_expression=compiled_rule.normalized_expression,
        dependencies=compiled_rule.dependencies,
        functions=compiled_rule.functions,
        helper_phases=compiled_rule.helper_phases,
        aggregate_helper=_to_aggregate_schema(compiled_rule.aggregate_helper),
        dsl_version=compiled_rule.dsl_version,
        source_type=compiled_rule.source_type,
        explainability_trace=_to_trace_schema(compiled_rule.explainability_trace),
    )


def _execute_rule(
    payload: ExecuteRuleRequest,
    rules_service: Annotated[RulesService, Depends(get_rules_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ExecuteRuleResponse:
    del principal
    compiled_rule, preview = rules_service.execute(
        artifact_id=payload.artifact_id,
        expression=payload.expression,
        target_column=payload.target_column,
        row=payload.row,
        seed=payload.seed,
        references=payload.references,
    )
    return ExecuteRuleResponse(
        artifact_id=compiled_rule.artifact_id,
        normalized_expression=compiled_rule.normalized_expression,
        value=preview.value,
        seed=preview.seed,
        row=preview.row,
        references=preview.references,
        diagnostics=[_to_diagnostic_schema(item) for item in preview.diagnostics],
        execution_mode="local_preview",
    )


@router.post("/preview", response_model=ExecuteRuleResponse)
def preview_rule(
    payload: ExecuteRuleRequest,
    rules_service: Annotated[RulesService, Depends(get_rules_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ExecuteRuleResponse:
    return _execute_rule(payload, rules_service, principal)


@router.post("/execute", response_model=ExecuteRuleResponse)
def execute_rule(
    payload: ExecuteRuleRequest,
    rules_service: Annotated[RulesService, Depends(get_rules_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> ExecuteRuleResponse:
    return _execute_rule(payload, rules_service, principal)
