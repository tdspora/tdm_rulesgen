from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rulesgen.compiler.limits import (
    DSLValueLimitExceeded,
    ValueSizer,
    apply_checked_binop,
    bounded_value_size,
    scalar_size,
)
from rulesgen.compiler.runtime_spec import RuntimeContext, build_runtime_locals


@given(st.text(alphabet=st.sampled_from(["A", "a", "#", "-"]), min_size=1, max_size=12))
def test_pattern_helper_respects_supported_alphabet(fmt: str) -> None:
    context = RuntimeContext(row={}, seed=11)
    pattern = build_runtime_locals(context)["pattern"]

    value = pattern(fmt)

    regex = "^" + fmt.replace("A", "[A-Z]").replace("a", "[a-z]").replace("#", "[0-9]") + "$"
    assert re.fullmatch(regex, value)


_SEQUENCES = st.one_of(
    st.text(max_size=8),
    st.binary(max_size=8),
    st.lists(st.one_of(st.integers(), st.text(max_size=4)), max_size=4),
    st.tuples(st.integers(), st.text(max_size=4)),
)


@given(
    sequence=_SEQUENCES,
    count=st.integers(min_value=-5, max_value=10**12),
    limit=st.integers(min_value=1, max_value=256),
    sequence_first=st.booleans(),
)
def test_checked_repetition_never_exceeds_limit(
    sequence: object, count: int, limit: int, sequence_first: bool
) -> None:
    left, right = (sequence, count) if sequence_first else (count, sequence)
    try:
        result = apply_checked_binop("Mult", left, right, limit=limit)
    except DSLValueLimitExceeded:
        return
    assert bounded_value_size(result, limit) <= max(limit, 1)


@given(
    left=st.text(max_size=40),
    right=st.text(max_size=40),
    limit=st.integers(min_value=1, max_value=64),
)
def test_checked_concatenation_never_exceeds_limit(left: str, right: str, limit: int) -> None:
    try:
        result = apply_checked_binop("Add", left, right, limit=limit)
    except DSLValueLimitExceeded:
        assert len(left) + len(right) > limit
        return
    assert len(result) <= limit


@given(
    left=st.lists(st.one_of(st.integers(), st.text(max_size=6)), max_size=6),
    right=st.lists(st.one_of(st.integers(), st.text(max_size=6)), max_size=6),
    limit=st.integers(min_value=1, max_value=32),
)
def test_checked_list_concatenation_matches_value_size(
    left: list[object], right: list[object], limit: int
) -> None:
    try:
        result = apply_checked_binop("Add", left, right, limit=limit)
    except DSLValueLimitExceeded:
        assert bounded_value_size(left + right, 10**6) > limit
        return
    assert bounded_value_size(result, limit) <= limit


@given(
    left=st.integers(min_value=-(10**80), max_value=10**80),
    right=st.integers(min_value=-(10**80), max_value=10**80),
    limit=st.integers(min_value=1, max_value=170),
)
def test_checked_integer_multiplication_never_exceeds_limit(
    left: int, right: int, limit: int
) -> None:
    try:
        result = apply_checked_binop("Mult", left, right, limit=limit)
    except DSLValueLimitExceeded:
        assert scalar_size(left) + scalar_size(right) > limit
        return
    assert bounded_value_size(result, limit) <= limit


def test_checked_integer_multiplication_is_rejected_before_it_runs() -> None:
    multiplied: list[int] = []

    class TrackedInt(int):
        def __mul__(self, other: object) -> int:
            assert isinstance(other, int)
            multiplied.append(other)
            return int(self) * other

    factor = TrackedInt(10**600)
    with pytest.raises(DSLValueLimitExceeded, match="Multiplication result exceeds"):
        apply_checked_binop("Mult", factor, factor, limit=1_000)

    assert multiplied == []
    assert apply_checked_binop("Mult", factor, 10, limit=1_000) == 10**601
    assert multiplied == [10]


def test_bounded_value_size_stops_early_on_shared_references() -> None:
    shared = "x" * 1_000
    huge = [shared] * 1_000_000

    assert bounded_value_size(huge, 5_000) > 5_000


def test_checked_modulo_rejects_text_formatting() -> None:
    with pytest.raises(TypeError, match="numeric modulo only"):
        apply_checked_binop("Mod", "%s", 1, limit=100)
    with pytest.raises(TypeError, match="numeric modulo only"):
        apply_checked_binop("Mod", b"%d", 1, limit=100)


@pytest.mark.parametrize("provider", ["__class__", "__init__", "seed_instance", "binary", "zip"])
def test_faker_helper_rejects_non_provider_attributes_without_validator(provider: str) -> None:
    faker = build_runtime_locals(RuntimeContext(row={}, seed=1))["faker"]

    with pytest.raises(ValueError, match="Unsupported Faker provider"):
        faker(provider)


_ELEMENTS = st.one_of(
    st.integers(min_value=-(10**40), max_value=10**40),
    st.floats(allow_nan=False),
    st.text(max_size=6),
    st.none(),
    st.booleans(),
)


def _plain(value: object) -> object:
    """Copy a value built by the checked helpers into plain lists and tuples."""
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


@given(
    items=st.lists(_ELEMENTS, max_size=5),
    nested=st.lists(_ELEMENTS, max_size=3),
    count=st.integers(min_value=0, max_value=6),
)
def test_carried_sizes_match_a_fresh_walk(
    items: list[object], nested: list[object], count: int
) -> None:
    sizer = ValueSizer(10**9)
    inner = sizer.checked_tuple(*nested)
    literal = sizer.checked_list(*items, inner)
    repeated = sizer.checked_binop("Mult", literal, count)
    combined = sizer.checked_binop("Add", repeated, sizer.checked_list(inner))

    for value in (inner, literal, repeated, combined):
        assert sizer.size(value) == bounded_value_size(_plain(value), 10**9)
