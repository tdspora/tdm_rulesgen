from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from rulesgen.compiler.runtime_spec import RuntimeContext, build_runtime_locals


@given(st.text(alphabet=st.sampled_from(["A", "a", "#", "-"]), min_size=1, max_size=12))
def test_pattern_helper_respects_supported_alphabet(fmt: str) -> None:
    context = RuntimeContext(row={}, seed=11)
    pattern = build_runtime_locals(context)["pattern"]

    value = pattern(fmt)

    regex = "^" + fmt.replace("A", "[A-Z]").replace("a", "[a-z]").replace("#", "[0-9]") + "$"
    assert re.fullmatch(regex, value)
