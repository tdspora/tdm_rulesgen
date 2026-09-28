"""Runtime cost limits shared by the DSL validator and the runtime helpers.

The validator bounds the *syntax* of a restricted DSL expression (length, depth,
node count). These limits bound what evaluating a validated expression may
*produce*, so a short expression cannot allocate gigabytes of memory or spin the
CPU for minutes (for example ``"a" * 800000000`` or ``regex("^A[0-9]{999999999}$")``).
"""

from __future__ import annotations

import itertools
import operator as _operator
import re
from collections.abc import Iterator
from typing import Any, Final

DEFAULT_MAX_VALUE_LENGTH: Final = 1_048_576
"""Default ceiling for the size of any value a DSL expression produces."""

MAX_REGEX_DIGITS: Final = 256
"""Largest digit count ``regex("^PREFIX[0-9]{N}$")`` may request."""

REGEX_HELPER_PATTERN: Final = re.compile(r"\^([A-Za-z-]+)\[0-9\]\{(\d+)\}\$")
"""The only pattern shape the ``regex(...)`` runtime helper supports."""

FAKER_PROVIDER_NAME_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")
"""Shape of a public Faker provider name accepted by ``faker(...)``."""

BLOCKED_FAKER_PROVIDERS: Final = frozenset({"binary", "image", "json_bytes", "tar", "zip"})
"""Faker providers that emit binary payloads (``binary`` defaults to 1 MiB per call)."""

_TEXT_TYPES: Final = (str, bytes, bytearray)
_SEQUENCE_TYPES: Final = (str, bytes, bytearray, list, tuple)
_CONTAINER_TYPES: Final = (list, tuple, set, frozenset, dict)
_EXHAUSTED: Final = object()


class DSLValueLimitExceeded(ValueError):
    """Raised when evaluating a DSL expression would produce an oversized value."""


class SizedList(list[Any]):
    """A list built by a DSL expression that carries its measured size."""

    __slots__ = ("rulesgen_units",)
    rulesgen_units: int


class SizedTuple(tuple[Any, ...]):
    """A tuple built by a DSL expression that carries its measured size."""

    rulesgen_units: int


def scalar_size(value: Any) -> int:
    """Approximate printed size of a value that is neither text nor a container."""
    if value is None or isinstance(value, bool):
        return 1
    if isinstance(value, int):
        # Decimal digits estimated from the bit length (log10(2) ~= 0.30103), so a
        # huge integer is sized without converting it to text.
        return (value.bit_length() * 30103) // 100000 + 1 + (1 if value < 0 else 0)
    if isinstance(value, float):
        return len(repr(value))
    try:
        return max(1, len(str(value)))
    except Exception:  # noqa: BLE001 - an unprintable object counts as one unit
        return 1


class ValueSizer:
    """Measures DSL values against a size limit for one rule evaluation.

    Sizes approximate the printed size of a value: text counts one unit per
    character or byte, integers count their decimal digits, other scalars count
    their printed length, and a container counts one unit plus, for each element,
    the element's size and one separator unit. Shared references are counted
    every time they appear, which matches the size of the value once serialized.

    Measuring stops as soon as a value exceeds the limit, so one measurement
    never takes more than about ``2 * (limit + 1)`` steps. Containers built by
    the DSL (:class:`SizedList`, :class:`SizedTuple`) carry their size, and the
    sizes of other containers (row values, helper results) are remembered by
    identity, so no container is walked twice during one evaluation.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        # Keyed by id(). The value is kept alive so its id cannot be reused; only
        # containers that did not come from DSL operators are stored here, and
        # those are referenced by the row or are small helper results anyway.
        self._known: dict[int, tuple[Any, int]] = {}

    def size(self, value: Any) -> int:
        """Return the size of ``value``; any result above the limit means "too large"."""
        if isinstance(value, _TEXT_TYPES):
            return max(1, len(value))
        if isinstance(value, SizedList | SizedTuple):
            return value.rulesgen_units
        if not isinstance(value, _CONTAINER_TYPES):
            return scalar_size(value)
        known = self._known.get(id(value))
        if known is not None and known[0] is value:
            return known[1]
        total = self._walk(value)
        self._known[id(value)] = (value, total)
        return total

    def ensure_within_limit(self, value: Any, *, context: str = "DSL value") -> None:
        """Raise :class:`DSLValueLimitExceeded` when ``value`` is larger than the limit."""
        if self.size(value) > self.limit:
            raise DSLValueLimitExceeded(
                f"{context} exceeds the configured limit of {self.limit} units."
            )

    def checked_binop(self, operator: str, left: Any, right: Any) -> Any:
        """Evaluate one DSL arithmetic operator with size checks on its result.

        ``operator`` is the ``ast.operator`` class name of a validated ``BinOp``
        node. Sequence repetition and concatenation are rejected before their
        result is built when it would exceed the limit, and integer products
        before they are computed when they could; ``%`` is numeric modulo only.
        """
        if operator == "Add":
            if isinstance(left, _SEQUENCE_TYPES) and isinstance(right, _SEQUENCE_TYPES):
                size = _overhead(left) + self._content_size(left) + self._content_size(right)
                if size > self.limit:
                    raise DSLValueLimitExceeded(
                        f"Concatenation result exceeds the configured limit of {self.limit} units."
                    )
                return _sized(_operator.add(left, right), size)
            return left + right
        if operator == "Sub":
            return left - right
        if operator == "Mult":
            for sequence, count in ((left, right), (right, left)):
                if isinstance(sequence, _SEQUENCE_TYPES) and isinstance(count, int):
                    size = _overhead(sequence) + self._content_size(sequence) * max(count, 0)
                    if size > self.limit:
                        raise DSLValueLimitExceeded(
                            "Sequence repetition result exceeds the configured limit of "
                            f"{self.limit} units."
                        )
                    return _sized(left * right, size)
            # A product has at most as many digits as its factors together, so
            # chained products of large row values are stopped before they run.
            if (
                isinstance(left, int)
                and isinstance(right, int)
                and scalar_size(left) + scalar_size(right) > self.limit
            ):
                raise DSLValueLimitExceeded(
                    f"Multiplication result exceeds the configured limit of {self.limit} units."
                )
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

    def checked_list(self, *items: Any) -> SizedList:
        """Build a DSL list literal, rejecting it when it exceeds the limit."""
        size = 1 + sum(self.size(item) + 1 for item in items)
        if size > self.limit:
            raise DSLValueLimitExceeded(
                f"List literal exceeds the configured limit of {self.limit} units."
            )
        value = SizedList(items)
        value.rulesgen_units = size
        return value

    def checked_tuple(self, *items: Any) -> SizedTuple:
        """Build a DSL tuple literal, rejecting it when it exceeds the limit."""
        size = 1 + sum(self.size(item) + 1 for item in items)
        if size > self.limit:
            raise DSLValueLimitExceeded(
                f"Tuple literal exceeds the configured limit of {self.limit} units."
            )
        value = SizedTuple(items)
        value.rulesgen_units = size
        return value

    def _content_size(self, sequence: Any) -> int:
        """Size of a sequence without its own container unit (an empty one is zero)."""
        if isinstance(sequence, _TEXT_TYPES):
            return len(sequence)
        return self.size(sequence) - 1

    def _walk(self, value: Any) -> int:
        total = 1
        pending: list[Iterator[Any]] = [_children(value)]
        while pending:
            item = next(pending[-1], _EXHAUSTED)
            if item is _EXHAUSTED:
                pending.pop()
                continue
            total += 1  # separator
            if isinstance(item, _TEXT_TYPES):
                total += max(1, len(item))
            elif isinstance(item, SizedList | SizedTuple):
                total += item.rulesgen_units
            elif isinstance(item, _CONTAINER_TYPES):
                known = self._known.get(id(item))
                if known is not None and known[0] is item:
                    total += known[1]
                else:
                    total += 1
                    pending.append(_children(item))
            else:
                total += scalar_size(item)
            if total > self.limit:
                break
        return total


def _sized(value: Any, size: int) -> Any:
    """Tag a list or tuple produced by a checked operator with its size."""
    if isinstance(value, list):
        sized_list = SizedList(value)
        sized_list.rulesgen_units = size
        return sized_list
    if isinstance(value, tuple):
        sized_tuple = SizedTuple(value)
        sized_tuple.rulesgen_units = size
        return sized_tuple
    return value


def _children(container: Any) -> Iterator[Any]:
    if isinstance(container, dict):
        return itertools.chain.from_iterable(container.items())
    return iter(container)


def _overhead(sequence: Any) -> int:
    """Units a sequence costs beyond its contents: zero for text, one for a container."""
    return 0 if isinstance(sequence, _TEXT_TYPES) else 1


def bounded_value_size(value: Any, limit: int) -> int:
    """Size of ``value`` as measured by :class:`ValueSizer`, stopping above ``limit``."""
    return ValueSizer(limit).size(value)


def ensure_value_within_limit(value: Any, limit: int, *, context: str = "DSL value") -> None:
    """Raise :class:`DSLValueLimitExceeded` when ``value`` is larger than ``limit``."""
    ValueSizer(limit).ensure_within_limit(value, context=context)


def apply_checked_binop(operator: str, left: Any, right: Any, *, limit: int) -> Any:
    """Evaluate one DSL arithmetic operator; see :meth:`ValueSizer.checked_binop`."""
    return ValueSizer(limit).checked_binop(operator, left, right)


def is_allowed_faker_provider_name(name: str) -> bool:
    """Return whether ``name`` may be passed to ``faker(...)``.

    Only lower-case public identifiers are accepted, which rules out dunder and
    private attributes of the Faker proxy; binary-producing providers are
    blocked. The runtime helper additionally checks that the name resolves to a
    real provider method.
    """
    return (
        FAKER_PROVIDER_NAME_PATTERN.fullmatch(name) is not None
        and name not in BLOCKED_FAKER_PROVIDERS
    )


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


__all__ = [
    "BLOCKED_FAKER_PROVIDERS",
    "DEFAULT_MAX_VALUE_LENGTH",
    "DSLValueLimitExceeded",
    "FAKER_PROVIDER_NAME_PATTERN",
    "MAX_REGEX_DIGITS",
    "REGEX_HELPER_PATTERN",
    "SizedList",
    "SizedTuple",
    "ValueSizer",
    "apply_checked_binop",
    "bounded_value_size",
    "ensure_value_within_limit",
    "is_allowed_faker_provider_name",
    "regex_digit_count",
    "scalar_size",
]
