"""DSL-fence validation for Rulesgen docs.

Every ` ```dsl ` fence in any doc must compile via
``rulesgen.library.compile_rule``. A fence opened with ` ```dsl !rejected `
documents a counter-example and must instead raise; the expected error
class is captured (if present) on the very next line as an HTML comment:
``<!-- expects: <ExceptionClassName> -->``.

There are zero ``dsl`` fences in the project today; this test
infrastructure exists so any future ``dsl`` example added to docs is
validated against the live compiler.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rulesgen.library import compile_rule

REPO_ROOT = Path(__file__).resolve().parents[2]

_FENCE_RE = re.compile(
    r"^```dsl(\s+!rejected)?\s*\n"
    r"(?:<!--\s*expects:\s*([A-Za-z_][A-Za-z0-9_.]*)\s*-->\s*\n)?"
    r"(.*?)^```",
    re.DOTALL | re.MULTILINE,
)

_SKIP_NAMES = frozenset({"CHANGELOG.md", "CLAUDE.md", "CLAUDE.local.md"})
_SKIP_PARTS = frozenset(
    {
        ".rulesgen-data",
        "~.rulesgen-data",
        "dist",
        "site",
        "node_modules",
        ".venv",
        ".git",
        ".github",
        ".claude",
        "tests",
    }
)


def _docs_to_check() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.md")
        if p.name not in _SKIP_NAMES and not (set(p.parts) & _SKIP_PARTS)
    )


def _extract_fences(text: str) -> list[tuple[bool, str | None, str]]:
    fences: list[tuple[bool, str | None, str]] = []
    for rejected_marker, expects, body in _FENCE_RE.findall(text):
        fences.append((bool(rejected_marker.strip()), expects or None, body))
    return fences


@pytest.mark.parametrize(
    "md",
    _docs_to_check(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_dsl_fences_validate(md: Path) -> None:
    fences = _extract_fences(md.read_text(encoding="utf-8"))
    if not fences:
        pytest.skip("no dsl fences in this doc")

    failures: list[str] = []
    for rejected, expects, body in fences:
        expression = body.strip()
        if not expression:
            failures.append("empty dsl fence")
            continue
        if rejected:
            try:
                compile_rule(expression)
            except Exception as exc:
                if expects and type(exc).__name__ != expects:
                    failures.append(
                        f"!rejected fence raised {type(exc).__name__}, expected {expects}: "
                        f"{expression!r}"
                    )
            else:
                failures.append(f"!rejected fence compiled unexpectedly: {expression!r}")
        else:
            try:
                compile_rule(expression)
            except Exception as exc:
                failures.append(
                    f"dsl fence failed to compile: {type(exc).__name__}: {exc}: {expression!r}"
                )

    assert not failures, "\n".join(failures)
