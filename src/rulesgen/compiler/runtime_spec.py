from __future__ import annotations

import ast
import copy
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import CodeType
from typing import Any, Final

from faker import Faker

from rulesgen.compiler.limits import (
    DEFAULT_MAX_VALUE_LENGTH,
    REGEX_HELPER_PATTERN,
    DSLValueLimitExceeded,
    apply_checked_binop,
    ensure_value_within_limit,
    regex_digit_count,
)

CHECKED_BINOP_HELPER: Final = "__rulesgen_binop__"
"""Internal runtime local that evaluates arithmetic operators with size checks.

The name is never reachable from DSL input: the validator rejects bare names and
calls to anything outside the helper whitelist, and the rewrite that introduces
this name runs only after validation.
"""


@dataclass(slots=True)
class RuntimeContext:
    row: dict[str, Any]
    seed: int
    references: dict[str, list[Any]] = field(default_factory=dict)
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    aggregate_helper_name: str | None = None
    aggregate_lookup: dict[Any, Any] | None = None
    max_value_length: int = DEFAULT_MAX_VALUE_LENGTH
    rng: random.Random = field(init=False)
    faker_instance: Faker = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.faker_instance = Faker()
        self.faker_instance.seed_instance(self.seed)


class _CheckedOperatorTransformer(ast.NodeTransformer):
    """Route every validated ``BinOp`` through :data:`CHECKED_BINOP_HELPER`."""

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        call = ast.Call(
            func=ast.Name(id=CHECKED_BINOP_HELPER, ctx=ast.Load()),
            args=[ast.Constant(value=type(node.op).__name__), node.left, node.right],
            keywords=[],
        )
        return ast.copy_location(call, node)


def compile_validated_expression(
    tree: ast.Expression, *, filename: str = "<rulesgen-dsl>"
) -> CodeType:
    """Compile a validated AST into the code object stored on a compiled rule.

    Arithmetic operators are rewritten into calls to the checked operator helper
    so their results are size-bounded at runtime. The caller's tree is not
    modified.
    """
    checked_tree = _CheckedOperatorTransformer().visit(copy.deepcopy(tree))
    ast.fix_missing_locations(checked_tree)
    return compile(checked_tree, filename=filename, mode="eval")


def build_runtime_locals(context: RuntimeContext) -> dict[str, Any]:
    limit = context.max_value_length

    def bounded_text(text: str, helper: str) -> str:
        if len(text) > limit:
            raise DSLValueLimitExceeded(
                f"{helper} result exceeds the configured limit of {limit} units."
            )
        return text

    def checked_binop(operator: str, left: Any, right: Any) -> Any:
        return apply_checked_binop(operator, left, right, limit=limit)

    def col(name: str) -> Any:
        return context.row.get(name)

    def coalesce(*args: Any) -> Any:
        for value in args:
            if value is not None:
                return value
        return None

    def lower(value: Any) -> str:
        return bounded_text(str(value).lower(), "lower()")

    def upper(value: Any) -> str:
        return bounded_text(str(value).upper(), "upper()")

    def concat(*args: Any) -> str:
        parts = [str(arg) for arg in args]
        if sum(len(part) for part in parts) > limit:
            raise DSLValueLimitExceeded(
                f"concat() result exceeds the configured limit of {limit} units."
            )
        return "".join(parts)

    def clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def optional(probability: float, value: Any) -> Any:
        return None if context.rng.random() < probability else value

    def randint(start: int, end: int) -> int:
        return context.rng.randint(start, end)

    def choice(sequence: list[Any], weights: list[float] | None = None) -> Any:
        population = list(sequence)
        if not population:
            raise ValueError("choice() requires a non-empty sequence.")
        if weights is None:
            return context.rng.choice(population)
        return context.rng.choices(population, weights=weights, k=1)[0]

    def faker(provider: str) -> Any:
        provider_fn = getattr(context.faker_instance, provider, None)
        if provider_fn is None or not callable(provider_fn):
            raise ValueError(f"Unsupported Faker provider: {provider}")
        value = provider_fn()
        ensure_value_within_limit(value, limit, context="faker() result")
        return value

    def pattern(fmt: str) -> str:
        bounded_text(fmt, "pattern()")
        output: list[str] = []
        for char in fmt:
            if char == "A":
                output.append(context.rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            elif char == "a":
                output.append(context.rng.choice("abcdefghijklmnopqrstuvwxyz"))
            elif char == "#":
                output.append(context.rng.choice("0123456789"))
            else:
                output.append(char)
        return "".join(output)

    def regex(value: str) -> str:
        match = REGEX_HELPER_PATTERN.fullmatch(value)
        if not match:
            raise ValueError("Only simple ^PREFIX[0-9]{N}$ regex patterns are supported.")
        prefix, count_str = match.groups()
        count = regex_digit_count(count_str)
        suffix = "".join(context.rng.choice("0123456789") for _ in range(count))
        return bounded_text(f"{prefix}{suffix}", "regex()")

    def fk(reference: str) -> Any:
        candidates = context.references.get(reference, [])
        if not candidates:
            raise ValueError(f"Reference set {reference!r} is empty.")
        return context.rng.choice(candidates)

    def group_sum(*, key: Any, value: Any) -> Any:
        del value
        if context.aggregate_helper_name != "group_sum" or context.aggregate_lookup is None:
            raise RuntimeError("group_sum is not supported by the current runtime context.")
        return context.aggregate_lookup.get(key)

    def group_count(*, key: Any) -> Any:
        if context.aggregate_helper_name != "group_count" or context.aggregate_lookup is None:
            raise RuntimeError("group_count is not supported by the current runtime context.")
        return context.aggregate_lookup.get(key)

    return {
        CHECKED_BINOP_HELPER: checked_binop,
        "choice": choice,
        "clamp": clamp,
        "coalesce": coalesce,
        "col": col,
        "concat": concat,
        "faker": faker,
        "fk": fk,
        "group_count": group_count,
        "group_sum": group_sum,
        "lower": lower,
        "optional": optional,
        "pattern": pattern,
        "randint": randint,
        "regex": regex,
        "upper": upper,
    }
