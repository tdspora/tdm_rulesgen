from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from rulesgen.compiler.parser import parse_expression
from rulesgen.compiler.runtime_spec import RuntimeContext, build_runtime_locals
from rulesgen.compiler.validator import DSLValidator
from rulesgen.domain.models import (
    ColumnSource,
    CompiledRule,
    Diagnostic,
    HelperPhase,
    SchemaColumnDefinition,
)
from rulesgen.errors import ValidationFailed


@dataclass(slots=True)
class GenerationRun:
    rows: list[dict[str, Any]]
    column_sources: dict[str, ColumnSource]
    row_rule_order: list[str] = field(default_factory=list)
    group_rule_order: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def execute_preview_rule(
    compiled_rule: CompiledRule,
    *,
    row: dict[str, Any],
    seed: int,
    references: dict[str, list[Any]],
    now: datetime | None = None,
    aggregate_helper_name: str | None = None,
    aggregate_lookup: dict[Any, Any] | None = None,
) -> Any:
    runtime_context = RuntimeContext(
        row=row,
        seed=seed,
        references=references,
        now=now or datetime.now(UTC),
        aggregate_helper_name=aggregate_helper_name,
        aggregate_lookup=aggregate_lookup,
    )
    locals_map = build_runtime_locals(runtime_context)
    return eval(compiled_rule.code_object, {"__builtins__": {}}, locals_map)


def execute_generation_plan(
    *,
    rows: list[dict[str, Any]],
    compiled_rules: list[CompiledRule],
    seed: int,
    references: dict[str, list[Any]],
    max_length: int,
    max_depth: int,
    max_nodes: int,
    schema: list[SchemaColumnDefinition] | None = None,
    now: datetime | None = None,
) -> GenerationRun:
    anchor_now = now or datetime.now(UTC)
    execution_schema = list(schema or [])
    materialized_rows = [_materialize_schema_columns(row, execution_schema) for row in rows]
    row_rules = [rule for rule in compiled_rules if _rule_phase(rule) is HelperPhase.ROW]
    group_rules = [rule for rule in compiled_rules if _rule_phase(rule) is HelperPhase.GROUP]

    row_order = _topological_order(row_rules)
    for rule in row_order:
        for row_index, row in enumerate(materialized_rows):
            try:
                row[rule.target_column or "value"] = execute_preview_rule(
                    rule,
                    row=row,
                    seed=_derive_seed(seed, rule.artifact_id, row_index),
                    references=references,
                    now=anchor_now,
                )
            except Exception as exc:  # noqa: BLE001
                target = rule.target_column or "<anonymous>"
                raise ValidationFailed(
                    f"Row-phase rule {target!r} failed at row {row_index}: {exc}"
                ) from exc

    group_order = _topological_order(group_rules)
    for rule in group_order:
        if rule.aggregate_helper is None:
            raise ValidationFailed("Group-phase rule is missing aggregate helper metadata.")
        lookup = _build_aggregate_lookup(
            rows=materialized_rows,
            compiled_rule=rule,
            seed=seed,
            references=references,
            max_length=max_length,
            max_depth=max_depth,
            max_nodes=max_nodes,
            now=anchor_now,
        )
        for row_index, row in enumerate(materialized_rows):
            try:
                row[rule.target_column or "value"] = execute_preview_rule(
                    rule,
                    row=row,
                    seed=_derive_seed(seed, rule.artifact_id, row_index),
                    references=references,
                    now=anchor_now,
                    aggregate_helper_name=rule.aggregate_helper.helper_name,
                    aggregate_lookup=lookup,
                )
            except Exception as exc:  # noqa: BLE001
                target = rule.target_column or "<anonymous>"
                raise ValidationFailed(
                    f"Group-phase rule {target!r} failed at row {row_index}: {exc}"
                ) from exc

    return GenerationRun(
        rows=materialized_rows,
        column_sources=_classify_columns(rows, compiled_rules, execution_schema),
        row_rule_order=[rule.target_column or rule.artifact_id for rule in row_order],
        group_rule_order=[rule.target_column or rule.artifact_id for rule in group_order],
    )


def _rule_phase(compiled_rule: CompiledRule) -> HelperPhase:
    if compiled_rule.aggregate_helper is not None:
        return HelperPhase.GROUP
    return HelperPhase.ROW


def _topological_order(compiled_rules: list[CompiledRule]) -> list[CompiledRule]:
    by_target = {
        rule.target_column: rule for rule in compiled_rules if rule.target_column is not None
    }
    pending = {rule.target_column or rule.artifact_id: rule for rule in compiled_rules}
    resolved: set[str] = set()
    ordered: list[CompiledRule] = []

    while pending:
        ready = [
            (name, rule)
            for name, rule in pending.items()
            if all(
                dependency not in by_target or dependency in resolved
                for dependency in rule.dependencies
                if dependency != rule.target_column
            )
        ]
        if not ready:
            cycle = ", ".join(sorted(pending))
            raise ValidationFailed(f"Rule dependency cycle detected: {cycle}")

        for name, rule in ready:
            ordered.append(rule)
            resolved.add(name)
            pending.pop(name)

    return ordered


def _materialize_schema_columns(
    row: dict[str, Any],
    schema: list[SchemaColumnDefinition],
) -> dict[str, Any]:
    materialized = dict(row)
    for column in schema:
        materialized.setdefault(column.name, None)
    return materialized


def _classify_columns(
    base_rows: list[dict[str, Any]],
    compiled_rules: list[CompiledRule],
    schema: list[SchemaColumnDefinition],
) -> dict[str, ColumnSource]:
    base_columns = {key for row in base_rows for key in row}
    sources = {column.name: ColumnSource.MODEL_GENERATED for column in schema}
    for column in base_columns:
        sources.setdefault(column, ColumnSource.MODEL_GENERATED)
    for rule in compiled_rules:
        if rule.target_column is None:
            continue
        if rule.target_column in base_columns:
            sources[rule.target_column] = ColumnSource.HYBRID
        else:
            sources[rule.target_column] = ColumnSource.RULE_GENERATED
    return sources


def _derive_seed(base_seed: int, artifact_id: str, row_index: int) -> int:
    digest = hashlib.sha256(f"{base_seed}:{artifact_id}:{row_index}".encode()).hexdigest()
    return int(digest[:16], 16)


def _build_aggregate_lookup(
    *,
    rows: list[dict[str, Any]],
    compiled_rule: CompiledRule,
    seed: int,
    references: dict[str, list[Any]],
    max_length: int,
    max_depth: int,
    max_nodes: int,
    now: datetime,
) -> dict[Any, Any]:
    aggregate_helper = compiled_rule.aggregate_helper
    if aggregate_helper is None:
        raise ValidationFailed("Aggregate lookup requested for non-aggregate rule.")

    key_code = _compile_expression(
        aggregate_helper.key_expression,
        max_length=max_length,
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    value_code = None
    if aggregate_helper.value_expression is not None:
        value_code = _compile_expression(
            aggregate_helper.value_expression,
            max_length=max_length,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )

    lookup: dict[Any, Any] = {}
    for row_index, row in enumerate(rows):
        context = RuntimeContext(
            row=row,
            seed=_derive_seed(seed, compiled_rule.artifact_id, row_index),
            references=references,
            now=now,
        )
        locals_map = build_runtime_locals(context)
        key = eval(key_code, {"__builtins__": {}}, locals_map)
        if key is None:
            continue
        if aggregate_helper.helper_name == "group_sum":
            if value_code is None:
                raise ValidationFailed("group_sum lookup is missing a value expression.")
            value = eval(value_code, {"__builtins__": {}}, locals_map)
            lookup[key] = lookup.get(key, 0) + (0 if value is None else value)
            continue
        lookup[key] = lookup.get(key, 0) + 1
    return lookup


def _compile_expression(expression: str, *, max_length: int, max_depth: int, max_nodes: int) -> Any:
    tree = parse_expression(expression, max_length=max_length)
    validated = DSLValidator(max_depth=max_depth, max_nodes=max_nodes).validate(tree)
    return compile(validated.tree, filename="<rulesgen-subexpression>", mode="eval")
