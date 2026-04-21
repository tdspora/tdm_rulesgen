from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rulesgen.compiler.parser import parse_expression
from rulesgen.compiler.validator import DSLValidator
from rulesgen.domain.models import (
    AggregateHelperSpec,
    CacheInsight,
    CompiledRule,
    CostBreakdown,
    ExplainabilityTrace,
    LLMRequestMetrics,
    SourceType,
    TokenUsage,
)
from rulesgen.execution.engine import execute_generation_plan


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit(
            "usage: python -m rulesgen.execution.opensandbox_runner <manifest> <result>"
        )

    manifest_path = Path(argv[1])
    result_path = Path(argv[2])
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    try:
        compiler_limits = dict(payload["compiler_limits"])
        compiled_rules = [
            _deserialize_compiled_rule(item, compiler_limits=compiler_limits)
            for item in payload["compiled_rules"]
        ]
        run = execute_generation_plan(
            rows=[dict(row) for row in payload["rows"]],
            compiled_rules=compiled_rules,
            seed=int(payload["seed"]),
            references=dict(payload.get("references", {})),
            max_length=int(compiler_limits["max_length"]),
            max_depth=int(compiler_limits["max_depth"]),
            max_nodes=int(compiler_limits["max_nodes"]),
            now=datetime.fromisoformat(payload["now"]),
        )
        output_rows_path = Path(payload["output_rows_path"])
        output_rows_path.write_text(
            json.dumps(run.rows, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        result_payload = {
            "success": True,
            "output_path": str(output_rows_path),
            "row_count": len(run.rows),
            "column_sources": {name: source.value for name, source in run.column_sources.items()},
            "row_rule_order": run.row_rule_order,
            "group_rule_order": run.group_rule_order,
            "diagnostics": [
                {
                    "level": item.level.value,
                    "code": item.code,
                    "message": item.message,
                    "location": item.location,
                }
                for item in run.diagnostics
            ],
        }
    except Exception as exc:  # noqa: BLE001
        result_payload = {
            "success": False,
            "error": str(exc),
        }

    result_path.write_text(
        json.dumps(result_payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return 0 if result_payload["success"] else 1


def _deserialize_compiled_rule(
    payload: dict[str, Any], *, compiler_limits: dict[str, Any]
) -> CompiledRule:
    normalized_expression = str(payload["normalized_expression"])
    tree = parse_expression(normalized_expression, max_length=int(compiler_limits["max_length"]))
    validated = DSLValidator(
        max_depth=int(compiler_limits["max_depth"]),
        max_nodes=int(compiler_limits["max_nodes"]),
    ).validate(tree)
    return CompiledRule(
        artifact_id=str(payload["artifact_id"]),
        target_column=payload.get("target_column"),
        expression=str(payload["expression"]),
        normalized_expression=validated.normalized_expression,
        dependencies=validated.dependencies,
        functions=validated.functions,
        helper_phases=validated.helper_phases,
        aggregate_helper=_deserialize_aggregate_helper(payload.get("aggregate_helper")),
        source_type=SourceType(payload.get("source_type", SourceType.DSL.value)),
        code_object=compile(validated.tree, filename="<rulesgen-dsl>", mode="eval"),
        dsl_version=str(payload.get("dsl_version", "v1")),
        explainability_trace=_deserialize_trace(payload.get("explainability_trace")),
        created_at=datetime.fromisoformat(payload["created_at"]),
    )


def _deserialize_aggregate_helper(payload: dict[str, Any] | None) -> AggregateHelperSpec | None:
    if payload is None:
        return None
    return AggregateHelperSpec(
        helper_name=str(payload["helper_name"]),
        key_expression=str(payload["key_expression"]),
        value_expression=payload.get("value_expression"),
    )


def _deserialize_trace(payload: dict[str, Any] | None) -> ExplainabilityTrace | None:
    if payload is None:
        return None
    return ExplainabilityTrace(
        source_type=SourceType(payload["source_type"]),
        source_text=str(payload["source_text"]),
        semantic_frame=dict(payload.get("semantic_frame", {})),
        dsl_candidate=payload.get("dsl_candidate"),
        normalized_expression=payload.get("normalized_expression"),
        prompt_audit_id=payload.get("prompt_audit_id"),
        prompt_audit_ids=list(payload.get("prompt_audit_ids", [])),
        prompt_template_version=payload.get("prompt_template_version"),
        model_name=payload.get("model_name"),
        provider_name=payload.get("provider_name"),
        metrics=_deserialize_llm_metrics(payload.get("metrics")),
        metadata=dict(payload.get("metadata", {})),
    )


def _deserialize_llm_metrics(payload: dict[str, Any] | None) -> LLMRequestMetrics | None:
    if payload is None:
        return None
    usage_payload = payload.get("usage")
    cost_payload = payload.get("cost")
    cache_payload = payload.get("cache")
    return LLMRequestMetrics(
        usage=(
            TokenUsage(
                prompt_tokens=usage_payload.get("prompt_tokens"),
                completion_tokens=usage_payload.get("completion_tokens"),
                total_tokens=usage_payload.get("total_tokens"),
                cached_tokens=usage_payload.get("cached_tokens"),
                raw=dict(usage_payload.get("raw", {})),
            )
            if isinstance(usage_payload, dict)
            else None
        ),
        cost=(
            CostBreakdown(
                total_cost=cost_payload.get("total_cost"),
                currency=str(cost_payload.get("currency", "USD")),
                raw=dict(cost_payload.get("raw", {})),
            )
            if isinstance(cost_payload, dict)
            else None
        ),
        latency_ms=payload.get("latency_ms"),
        attempts=int(payload.get("attempts", 1)),
        cache=(
            CacheInsight(
                backend=cache_payload.get("backend"),
                enabled=bool(cache_payload.get("enabled", False)),
                hit=bool(cache_payload.get("hit", False)),
                scope_key=cache_payload.get("scope_key"),
                similarity=cache_payload.get("similarity"),
                metadata=dict(cache_payload.get("metadata", {})),
            )
            if isinstance(cache_payload, dict)
            else None
        ),
        metadata=dict(payload.get("metadata", {})),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
