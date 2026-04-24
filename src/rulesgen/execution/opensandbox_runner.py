from __future__ import annotations

import csv
import io
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
    SchemaColumnDefinition,
    SchemaColumnSource,
    SourceType,
    TokenUsage,
)
from rulesgen.domain.uploads import DatasetInputFormat
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
        schema = [_deserialize_schema_column(item) for item in payload.get("schema", [])]
        run = execute_generation_plan(
            rows=_load_rows(
                input_source=dict(payload["input_source"]),
                schema=schema,
            ),
            compiled_rules=compiled_rules,
            seed=int(payload["seed"]),
            references=dict(payload.get("references", {})),
            max_length=int(compiler_limits["max_length"]),
            max_depth=int(compiler_limits["max_depth"]),
            max_nodes=int(compiler_limits["max_nodes"]),
            schema=schema,
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


def _load_rows(
    *,
    input_source: dict[str, Any],
    schema: list[SchemaColumnDefinition],
) -> list[dict[str, Any]]:
    input_path = Path(str(input_source["path"]))
    input_format = DatasetInputFormat(str(input_source["format"]))
    if input_format is DatasetInputFormat.JSON:
        rows = _load_json_rows(input_path)
    else:
        rows = _load_csv_rows(input_path, schema=schema)
    expected_row_count = int(input_source.get("row_count", len(rows)))
    if expected_row_count != len(rows):
        raise ValueError("Staged input row_count metadata did not match the number of loaded rows.")
    return rows


def _load_json_rows(input_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("JSON input sources must contain an array of row objects.")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("JSON input sources must contain only row objects.")
        rows.append({str(key): value for key, value in item.items()})
    if not rows:
        raise ValueError("Dataset input files must contain at least one row.")
    return rows


def _load_csv_rows(
    input_path: Path,
    *,
    schema: list[SchemaColumnDefinition],
) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(input_path.read_text(encoding="utf-8")))
    if reader.fieldnames is None:
        raise ValueError("CSV input sources must include a header row.")
    schema_by_name = {column.name: column for column in schema}
    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        if raw_row is None:
            continue
        if None in raw_row:
            raise ValueError("CSV input rows must match the header columns.")
        if all(value in (None, "") for value in raw_row.values()):
            continue
        row: dict[str, Any] = {}
        for key, value in raw_row.items():
            assert key is not None
            row[str(key)] = _coerce_csv_value(value, schema_by_name.get(str(key)))
        rows.append(row)
    if not rows:
        raise ValueError("Dataset input files must contain at least one row.")
    return rows


def _coerce_csv_value(value: str | None, column: SchemaColumnDefinition | None) -> Any:
    if value is None:
        return None
    stripped = value.strip()
    if column is not None and stripped == "" and column.nullable:
        return None
    if column is None:
        return value
    data_type = column.data_type.strip().upper()
    if data_type in {"INT", "INTEGER", "BIGINT", "SMALLINT"}:
        return int(stripped)
    if data_type in {"FLOAT", "DOUBLE", "DECIMAL", "NUMBER", "NUMERIC"}:
        return float(stripped)
    if data_type in {"BOOL", "BOOLEAN"}:
        lowered = stripped.lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
        raise ValueError(f"Could not parse boolean value {value!r} for CSV input.")
    return value


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


def _deserialize_schema_column(payload: dict[str, Any]) -> SchemaColumnDefinition:
    return SchemaColumnDefinition(
        name=str(payload["name"]),
        data_type=str(payload["data_type"]),
        nullable=bool(payload["nullable"]),
        source=SchemaColumnSource(str(payload["source"])),
        notes=payload.get("notes"),
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
