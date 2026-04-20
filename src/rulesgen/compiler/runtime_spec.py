from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from faker import Faker


@dataclass(slots=True)
class RuntimeContext:
    row: dict[str, Any]
    seed: int
    references: dict[str, list[Any]] = field(default_factory=dict)
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    aggregate_helper_name: str | None = None
    aggregate_lookup: dict[Any, Any] | None = None
    rng: random.Random = field(init=False)
    faker_instance: Faker = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.faker_instance = Faker()
        self.faker_instance.seed_instance(self.seed)


def build_runtime_locals(context: RuntimeContext) -> dict[str, Any]:
    def col(name: str) -> Any:
        return context.row.get(name)

    def coalesce(*args: Any) -> Any:
        for value in args:
            if value is not None:
                return value
        return None

    def lower(value: Any) -> str:
        return str(value).lower()

    def upper(value: Any) -> str:
        return str(value).upper()

    def concat(*args: Any) -> str:
        return "".join(str(arg) for arg in args)

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
        return provider_fn()

    def pattern(fmt: str) -> str:
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
        match = re.fullmatch(r"\^([A-Za-z-]+)\[0-9\]\{(\d+)\}\$", value)
        if not match:
            raise ValueError("Only simple ^PREFIX[0-9]{N}$ regex patterns are supported.")
        prefix, count_str = match.groups()
        count = int(count_str)
        suffix = "".join(context.rng.choice("0123456789") for _ in range(count))
        return f"{prefix}{suffix}"

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
