from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rulesgen.compiler.limits import (
    DSLValueLimitExceeded,
    apply_checked_binop,
    bounded_value_size,
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
