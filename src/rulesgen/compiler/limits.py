"""Runtime cost limits shared by the DSL validator and the runtime helpers.

The validator bounds the *syntax* of a restricted DSL expression (length, depth,
node count). These limits bound what evaluating a validated expression may
*produce*, so a short expression cannot allocate gigabytes of memory or spin the
CPU for minutes (for example ``"a" * 800000000`` or ``regex("^A[0-9]{999999999}$")``).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Final

DEFAULT_MAX_VALUE_LENGTH: Final = 1_048_576
"""Default ceiling for the size of any value a DSL expression produces."""

MAX_REGEX_DIGITS: Final = 256
"""Largest digit count ``regex("^PREFIX[0-9]{N}$")`` may request."""

REGEX_HELPER_PATTERN: Final = re.compile(r"\^([A-Za-z-]+)\[0-9\]\{(\d+)\}\$")
"""The only pattern shape the ``regex(...)`` runtime helper supports."""

_TEXT_TYPES: Final = (str, bytes, bytearray)
_SEQUENCE_TYPES: Final = (str, bytes, bytearray, list, tuple)
_EXHAUSTED: Final = object()


class DSLValueLimitExceeded(ValueError):
    """Raised when evaluating a DSL expression would produce an oversized value."""


def bounded_value_size(value: Any, limit: int) -> int:
    """Return the expanded size of ``value``, stopping as soon as it exceeds ``limit``.

    Text counts one unit per character or byte; containers count themselves plus
    the expanded size of every element. Shared references are counted each time
    they appear, which matches the size of the value once it is serialized. Every
    visited item counts at least one unit, so the walk never takes more than
    ``limit + 1`` steps.
    """
    if isinstance(value, _TEXT_TYPES):
        return max(1, len(value))
    if not isinstance(value, list | tuple | set | frozenset | dict):
        return 1

    total = 0
    pending: list[Iterator[Any]] = [iter((value,))]
    while pending:
        item = next(pending[-1], _EXHAUSTED)
        if item is _EXHAUSTED:
            pending.pop()
            continue
        if isinstance(item, _TEXT_TYPES):
            total += max(1, len(item))
        elif isinstance(item, dict):
            total += 1
            pending.append(iter(item.items()))
        elif isinstance(item, list | tuple | set | frozenset):
            total += 1
            pending.append(iter(item))
        else:
            total += 1
        if total > limit:
            break
    return total


def regex_digit_count(count_text: str) -> int:
    """Return the digit count a ``regex(...)`` pattern requests.

    Raises :class:`DSLValueLimitExceeded` when the count is above
    :data:`MAX_REGEX_DIGITS`. Leading zeros are ignored, and oversized counts are
    rejected before any integer conversion.
    """
    digits = count_text.lstrip("0") or "0"
    if len(digits) > len(str(MAX_REGEX_DIGITS)) or int(digits) > MAX_REGEX_DIGITS:
        raise DSLValueLimitExceeded(f"regex() supports at most {MAX_REGEX_DIGITS} digits.")
    return int(digits)


def ensure_value_within_limit(value: Any, limit: int, *, context: str = "DSL value") -> None:
    """Raise :class:`DSLValueLimitExceeded` when ``value`` is larger than ``limit``."""
    if bounded_value_size(value, limit) > limit:
        raise DSLValueLimitExceeded(f"{context} exceeds the configured limit of {limit} units.")


def apply_checked_binop(operator: str, left: Any, right: Any, *, limit: int) -> Any:
    """Evaluate one DSL arithmetic operator with size checks on its result.

    ``operator`` is the ``ast.operator`` class name of a validated ``BinOp`` node.
    Sequence repetition and concatenation are rejected when their result would
    exceed ``limit``; ``%`` is numeric modulo only.
    """
    if operator == "Add":
        if isinstance(left, _SEQUENCE_TYPES) and isinstance(right, _SEQUENCE_TYPES):
            size = _overhead(left) + _content_size(left, limit) + _content_size(right, limit)
            if size > limit:
                raise DSLValueLimitExceeded(
                    f"Concatenation result exceeds the configured limit of {limit} units."
                )
        return left + right
    if operator == "Sub":
        return left - right
    if operator == "Mult":
        _check_repetition(left, right, limit)
        _check_repetition(right, left, limit)
        return left * right
    if operator == "Div":
        return left / right
    if operator == "Mod":
        if isinstance(left, _TEXT_TYPES):
            raise TypeError(
                "The DSL % operator is numeric modulo only; use concat() to build strings."
            )
        return left % right
    raise ValueError(f"Unsupported DSL operator: {operator!r}.")


def _check_repetition(sequence: Any, count: Any, limit: int) -> None:
    if not isinstance(sequence, _SEQUENCE_TYPES) or not isinstance(count, int):
        return
    if count <= 0:
        return
    if _overhead(sequence) + _content_size(sequence, limit) * count > limit:
        raise DSLValueLimitExceeded(
            f"Sequence repetition result exceeds the configured limit of {limit} units."
        )


def _overhead(sequence: Any) -> int:
    """Units :func:`bounded_value_size` charges a sequence beyond its contents."""
    return 0 if isinstance(sequence, _TEXT_TYPES) else 1


def _content_size(sequence: Any, limit: int) -> int:
    """Size contributed by the contents of a sequence (an empty sequence is zero)."""
    if isinstance(sequence, _TEXT_TYPES):
        return len(sequence)
    total = 0
    for item in sequence:
        total += bounded_value_size(item, limit)
        if total > limit:
            break
    return total


__all__ = [
    "DEFAULT_MAX_VALUE_LENGTH",
    "DSLValueLimitExceeded",
    "MAX_REGEX_DIGITS",
    "REGEX_HELPER_PATTERN",
    "apply_checked_binop",
    "bounded_value_size",
    "ensure_value_within_limit",
    "regex_digit_count",
]
