from __future__ import annotations

import ast
import copy
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import CodeType
from typing import Any, Final

from faker import Faker
from faker.providers import BaseProvider

from rulesgen.compiler.limits import (
    DEFAULT_MAX_VALUE_LENGTH,
    REGEX_HELPER_PATTERN,
    DSLValueLimitExceeded,
    ValueSizer,
    is_allowed_faker_provider_name,
    regex_digit_count,
)

CHECKED_BINOP_HELPER: Final = "__rulesgen_binop__"
CHECKED_LIST_HELPER: Final = "__rulesgen_list__"
CHECKED_TUPLE_HELPER: Final = "__rulesgen_tuple__"
"""Internal runtime locals that evaluate operators and literals with size checks.

These names are never reachable from DSL input: the validator rejects bare names
and calls to anything outside the helper whitelist, and the rewrite that
introduces them runs only after validation.
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
    sizer: ValueSizer = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.faker_instance = Faker()
        self.faker_instance.seed_instance(self.seed)
        self.sizer = ValueSizer(self.max_value_length)


class _CheckedOperatorTransformer(ast.NodeTransformer):
    """Route validated operators and list/tuple literals through checked helpers."""

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        call = ast.Call(
            func=ast.Name(id=CHECKED_BINOP_HELPER, ctx=ast.Load()),
            args=[ast.Constant(value=type(node.op).__name__), node.left, node.right],
            keywords=[],
        )
        return ast.copy_location(call, node)

    def visit_List(self, node: ast.List) -> ast.AST:
        return self._checked_literal(node, CHECKED_LIST_HELPER)

    def visit_Tuple(self, node: ast.Tuple) -> ast.AST:
        return self._checked_literal(node, CHECKED_TUPLE_HELPER)

    def _checked_literal(self, node: ast.List | ast.Tuple, helper: str) -> ast.AST:
        self.generic_visit(node)
        call = ast.Call(
            func=ast.Name(id=helper, ctx=ast.Load()),
            args=list(node.elts),
            keywords=[],
        )
        return ast.copy_location(call, node)


def compile_validated_expression(
    tree: ast.Expression, *, filename: str = "<rulesgen-dsl>"
) -> CodeType:
    """Compile a validated AST into the code object stored on a compiled rule.

    Arithmetic operators and list/tuple literals are rewritten into calls to the
    checked runtime helpers so their results are size-bounded at runtime. The
    caller's tree is not modified.
    """
    checked_tree = _CheckedOperatorTransformer().visit(copy.deepcopy(tree))
    ast.fix_missing_locations(checked_tree)
    return compile(checked_tree, filename=filename, mode="eval")


def build_runtime_locals(context: RuntimeContext) -> dict[str, Any]:
    limit = context.max_value_length
    sizer = context.sizer

    def bounded_text(text: str, helper: str) -> str:
        if len(text) > limit:
            raise DSLValueLimitExceeded(
                f"{helper} result exceeds the configured limit of {limit} units."
            )
        return text

    def col(name: str) -> Any:
        return context.row.get(name)

    def coalesce(*args: Any) -> Any:
        for value in args:
            if value is not None:
                return value
        return None

    def lower(value: Any) -> str:
        # Measure before converting, so str() never renders an oversized value.
        sizer.ensure_within_limit(value, context="lower() argument")
        return bounded_text(str(value).lower(), "lower()")

    def upper(value: Any) -> str:
        sizer.ensure_within_limit(value, context="upper() argument")
        return bounded_text(str(value).upper(), "upper()")

    def concat(*args: Any) -> str:
        if sum(sizer.size(arg) for arg in args) > limit:
            raise DSLValueLimitExceeded(
                f"concat() arguments exceed the configured limit of {limit} units."
            )
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
        if not isinstance(provider, str) or not is_allowed_faker_provider_name(provider):
            raise ValueError(f"Unsupported Faker provider: {provider!r}")
        try:
            provider_fn = getattr(context.faker_instance, provider)
        except (AttributeError, TypeError) as exc:
            raise ValueError(f"Unsupported Faker provider: {provider!r}") from exc
        # Only methods of real Faker providers are callable; this excludes the
        # Faker proxy and Generator plumbing such as seed_instance or add_provider.
        if not callable(provider_fn) or not isinstance(
            getattr(provider_fn, "__self__", None), BaseProvider
        ):
            raise ValueError(f"Unsupported Faker provider: {provider!r}")
        value = provider_fn()
        sizer.ensure_within_limit(value, context="faker() result")
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
        CHECKED_BINOP_HELPER: sizer.checked_binop,
        CHECKED_LIST_HELPER: sizer.checked_list,
        CHECKED_TUPLE_HELPER: sizer.checked_tuple,
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
