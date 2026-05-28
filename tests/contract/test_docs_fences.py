"""Sybil-based executor for Python code fences in user-facing docs.

Scope is intentionally narrow at first: only files under ``docs/`` are
collected for sybil execution. Repo-root and requirements docs (``README.md``,
``requirements/NL-to-Python-Generation-*.md``, ``CONTRIBUTING.md``) currently
contain illustrative Python fences that pre-date this contract and have not been
audited for sybil-readiness; expanding sybil coverage to them is a
follow-up to the technical-writer harness rollout. Until then, those docs
are still validated by the other ``tests/contract/test_docs_*.py`` tests
(links, glossary, cross-ref, DSL).

A fence is opted out of execution by placing ``<!-- skip: next -->`` on
the line directly above it (sybil's standard skip directive). A range
can be skipped with ``<!-- skip: start --> ... <!-- skip: end -->``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip(
    "sybil",
    reason="sybil is a dev dependency; install via `uv sync --extra dev --locked`",
)

from sybil import Sybil  # noqa: E402
from sybil.parsers.markdown import PythonCodeBlockParser, SkipParser  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = REPO_ROOT / "docs"

_SYBIL = Sybil(
    parsers=[PythonCodeBlockParser(), SkipParser()],
    patterns=["*.md"],
)

_EXCLUDED_PARTS = frozenset(
    {
        "node_modules",
        ".venv",
        ".rulesgen-data",
        "~.rulesgen-data",
        "dist",
        "site",
    }
)


def _doc_paths() -> list[Path]:
    if not DOCS_ROOT.exists():
        return []
    return sorted(
        p
        for p in DOCS_ROOT.rglob("*.md")
        if not (set(p.parts) & _EXCLUDED_PARTS) and not p.name.startswith(".")
    )


@pytest.mark.parametrize(
    "doc_path",
    _doc_paths(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_python_fences_evaluate(doc_path: Path) -> None:
    document = _SYBIL.parse(doc_path)
    for example in document.examples():
        example.evaluate()
