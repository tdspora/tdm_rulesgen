"""Internal Markdown link integrity for Rulesgen docs.

For every Markdown file outside generated / vendored / runtime trees,
extract every relative link (``[label](path)``) and assert that the
target path resolves from the source file's directory. External links
(``http``, ``https``, ``mailto``) are validated by the lychee CI step,
not by this test.

``CHANGELOG.md`` is excluded because it is owned by
``python-semantic-release`` and its links are auto-generated.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(\s*([^)\s]+?)(?:\s+\"[^\"]*\")?\s*\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+?)(?:\s+\"[^\"]*\")?\s*\)")

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


def _strip_anchor_and_query(url: str) -> str:
    for sep in ("#", "?"):
        idx = url.find(sep)
        if idx != -1:
            url = url[:idx]
    return url


def _md_files() -> list[Path]:
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.md")
        if p.name not in _SKIP_NAMES and not (set(p.parts) & _SKIP_PARTS)
    )


@pytest.mark.parametrize(
    "md",
    _md_files(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_relative_links_resolve(md: Path) -> None:
    text = md.read_text(encoding="utf-8")
    candidates: list[str] = []
    candidates.extend(LINK_RE.findall(text))
    candidates.extend(IMAGE_RE.findall(text))

    unresolved: list[str] = []
    for raw in candidates:
        url = _strip_anchor_and_query(raw)
        if not url or url.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        if url.startswith("<") and url.endswith(">"):
            url = url[1:-1]
        target = (md.parent / url).resolve()
        if not target.exists():
            unresolved.append(raw)
    assert not unresolved, f"{md.relative_to(REPO_ROOT)}: unresolved relative links: {unresolved}"
