from __future__ import annotations

from collections.abc import Sequence

from rulesgen.domain.generation import RuleDraft
from rulesgen.domain.models import LLMRequestMetrics, SchemaColumnDefinition, SourceType
from rulesgen.schemas.datasets import RuleDraftSchema
from rulesgen.schemas.jobs import JobRuleDraftSchema
from rulesgen.schemas.rules import (
    CacheInsightSchema,
    CostBreakdownSchema,
    LLMRequestMetricsSchema,
    ParseRuleRequest,
    RequestSourceTypeSchema,
    SchemaColumnDefinitionSchema,
    TokenUsageSchema,
)


def to_domain_source_type(source_type: RequestSourceTypeSchema) -> SourceType:
    if source_type is RequestSourceTypeSchema.NATURAL_LANGUAGE:
        return SourceType.NATURAL_LANGUAGE
    return SourceType.DSL


def to_domain_schema(
    schema: list[SchemaColumnDefinitionSchema],
) -> list[SchemaColumnDefinition]:
    return [
        SchemaColumnDefinition(
            name=item.name,
            data_type=item.type,
            nullable=item.nullable,
            source=item.source,
            notes=item.notes,
        )
        for item in schema
    ]


def to_parse_request_args(payload: ParseRuleRequest) -> tuple[str, SourceType, str | None]:
    embedded_rule_columns = [item for item in payload.schema_ if item.has_rule_definition()]
    if embedded_rule_columns:
        item = embedded_rule_columns[0]
        if item.artifact_id is not None:
            raise ValueError("rules/parse does not support artifact_id schema rows.")
        assert item.source_text is not None
        assert item.source_type is not None
        return (
            item.source_text,
            to_domain_source_type(item.source_type),
            item.name,
        )

    assert payload.source_text is not None
    assert payload.source_type is not None
    return (
        payload.source_text,
        to_domain_source_type(payload.source_type),
        payload.target_column,
    )


def to_domain_rule_drafts_from_schema(
    schema: list[SchemaColumnDefinitionSchema],
) -> list[RuleDraft]:
    drafts: list[RuleDraft] = []
    for item in schema:
        if not item.has_rule_definition():
            continue
        if item.artifact_id is not None and item.source_text is None and item.source_type is None:
            drafts.append(
                RuleDraft(
                    target_column=item.name,
                    artifact_id=item.artifact_id,
                )
            )
            continue

        assert item.source_text is not None
        assert item.source_type is not None
        domain_source_type = to_domain_source_type(item.source_type)
        drafts.append(
            RuleDraft(
                target_column=item.name,
                source_type=domain_source_type,
                source_text=(
                    item.source_text
                    if domain_source_type is SourceType.NATURAL_LANGUAGE
                    else None
                ),
                expression=(
                    item.source_text
                    if domain_source_type is SourceType.DSL
                    else None
                ),
                artifact_id=item.artifact_id,
            )
        )
    return drafts


def to_domain_rule_drafts(
    rules: Sequence[RuleDraftSchema | JobRuleDraftSchema],
) -> list[RuleDraft]:
    drafts: list[RuleDraft] = []
    for item in rules:
        domain_source_type = to_domain_source_type(item.source_type)
        drafts.append(
            RuleDraft(
                target_column=item.target_column,
                source_type=domain_source_type,
                source_text=(
                    item.source_text
                    if domain_source_type is SourceType.NATURAL_LANGUAGE
                    else None
                ),
                expression=(
                    item.expression
                    if item.expression is not None
                    else item.source_text if domain_source_type is SourceType.DSL else None
                ),
                artifact_id=item.artifact_id,
            )
        )
    return drafts


def to_llm_metrics_schema(metrics: LLMRequestMetrics | None) -> LLMRequestMetricsSchema | None:
    if metrics is None:
        return None
    return LLMRequestMetricsSchema(
        usage=(
            TokenUsageSchema(
                prompt_tokens=metrics.usage.prompt_tokens,
                completion_tokens=metrics.usage.completion_tokens,
                total_tokens=metrics.usage.total_tokens,
                cached_tokens=metrics.usage.cached_tokens,
                raw=metrics.usage.raw,
            )
            if metrics.usage is not None
            else None
        ),
        cost=(
            CostBreakdownSchema(
                total_cost=metrics.cost.total_cost,
                currency=metrics.cost.currency,
                raw=metrics.cost.raw,
            )
            if metrics.cost is not None
            else None
        ),
        latency_ms=metrics.latency_ms,
        attempts=metrics.attempts,
        cache=(
            CacheInsightSchema(
                backend=metrics.cache.backend,
                enabled=metrics.cache.enabled,
                hit=metrics.cache.hit,
                scope_key=metrics.cache.scope_key,
                similarity=metrics.cache.similarity,
                metadata=metrics.cache.metadata,
            )
            if metrics.cache is not None
            else None
        ),
        metadata=metrics.metadata,
    )
