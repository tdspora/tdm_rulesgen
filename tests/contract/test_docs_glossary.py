"""Glossary-alignment lint for Rulesgen docs.

``docs/agent-harness/glossary.md`` is the single source of truth for
project vocabulary. Every ``[[term]]`` reference appearing in any other
doc must resolve to a term defined in the glossary.

Defined terms are extracted from glossary table rows whose first column
begins with ``**TERM**`` or ``**[[TERM]]**``. The matcher is forgiving:
case-insensitive, pipe-syntax aware (``[[a|b]]`` → ``b``), and tolerant
of singular/plural mismatch (trailing ``s`` may be added or removed).
Glossary-internal references are not checked here — the glossary file
is curated by hand and is the authority for its own cross-references.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = REPO_ROOT / "docs" / "agent-harness" / "glossary.md"

_TERM_DEF_RE = re.compile(r"^\|\s*\*\*(?:\[\[)?([^*\]]+?)(?:\]\])?\*\*", re.MULTILINE)
_REF_RE = re.compile(r"\[\[([^\]]+?)\]\]")

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


def _normalize(term: str) -> str:
    term = term.strip()
    if "|" in term:
        term = term.split("|")[-1].strip()
    return term.lower()


def _canonical_terms() -> set[str]:
    if not GLOSSARY.exists():
        return set()
    text = GLOSSARY.read_text(encoding="utf-8")
    norm: set[str] = set()
    for raw in _TERM_DEF_RE.findall(text):
        cleaned = raw.strip().rstrip(".")
        norm.add(_normalize(cleaned))
        head = cleaned.split("(", 1)[0].strip()
        if head:
            norm.add(_normalize(head))
    return norm


def _matches(reference: str, canonical: set[str]) -> bool:
    n = _normalize(reference)
    if n in canonical:
        return True
    if n.endswith("s") and n[:-1] in canonical:
        return True
    if (n + "s") in canonical:
        return True
    return False


def _docs_to_lint() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.md")
        if p != GLOSSARY and p.name not in _SKIP_NAMES and not (set(p.parts) & _SKIP_PARTS)
    )


_CANONICAL = _canonical_terms()


@pytest.mark.parametrize(
    "md",
    _docs_to_lint(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_bracket_refs_resolve_to_glossary(md: Path) -> None:
    text = md.read_text(encoding="utf-8")
    unresolved: list[str] = []
    for raw_ref in _REF_RE.findall(text):
        if not _matches(raw_ref, _CANONICAL):
            unresolved.append(raw_ref)
    assert not unresolved, (
        f"{md.relative_to(REPO_ROOT)}: [[refs]] not defined in glossary.md: "
        f"{sorted(set(unresolved))}"
    )


def test_glossary_has_canonical_terms() -> None:
    """Sanity: the glossary itself must define a non-trivial vocabulary."""
    assert len(_CANONICAL) > 20, (
        f"Expected the glossary to define many canonical terms, "
        f"got only {len(_CANONICAL)}: {sorted(_CANONICAL)[:10]}..."
    )
