---
name: rulesgen-docs-testing
description: Use for testing Rulesgen documentation — executes Markdown code fences via Sybil, validates link integrity, lints glossary usage, and cross-checks docs against Settings, schemas, and routes.
---

# Rulesgen Docs Testing

## Purpose

Documentation is a public, executable artifact. This skill validates that:

- Python code fences in `*.md` files actually run.
- Internal links resolve to files / anchors that exist.
- External links are reachable HTTPS resources (gated; not on every PR).
- Every domain term used in docs appears in `docs/agent-harness/glossary.md`.
- Every documented Settings field exists in `src/rulesgen/core/config.py`.
- Every documented endpoint exists under `src/rulesgen/api/v1/`.
- Every DSL fence parses and validates via `rulesgen.library`.

## Tooling matrix

| Check | Tool | Test file |
|---|---|---|
| Executable Python fences | `sybil` (dev dep) | `tests/contract/test_docs_fences.py` |
| Internal link integrity | stdlib `pathlib` + `pytest` | `tests/contract/test_docs_links.py` |
| External link integrity | `markdown-link-check` (or `lychee`) | CI step, gated on schedule |
| Glossary lint | stdlib `re` + `pytest` | `tests/contract/test_docs_glossary.py` |
| Settings / schema / route cross-check | stdlib `importlib` + `pytest` | `tests/contract/test_docs_crossref.py` |
| DSL examples | `rulesgen.library` + `pytest` | `tests/contract/test_docs_dsl.py` |

All tests live in `tests/contract/` because they pin the public, documented contract — the same place RFC 7807 Problem Details tests live.

## Required approval before installing tooling

Adding `sybil` (Python dev dep) or `markdown-link-check` / `lychee` (CI step) is a **dependency / CI change** and an **Approval Contract** escalation per `CLAUDE.md`. Before running any `uv add` or `.github/workflows/ci.yml` edit:

1. Print on a single line: `APPROVAL REQUIRED: add sybil to [project.optional-dependencies.dev] and a Markdown link checker (markdown-link-check or lychee) as a CI step`.
2. Stop and yield the turn.
3. Wait for the human to type exactly `approved`, `approved: <constraint>`, or `deny`. Anything else (silence, `ok`, thumbs-up, emoji, paraphrase) is **not** approval.
4. Only after `approved`:
   - `uv add --dev sybil` (the harness allows `Bash(uv add*)` only via the `ask` permission tier — the user will see a prompt).
   - Update `.github/workflows/ci.yml` to install the link checker as a CI step.
   - Commit `pyproject.toml` and `uv.lock` together with the CI change in a single `chore(deps): ...` commit.

Until approved, the rest of this skill describes the **target** workflow; the tests cannot yet run.

## Sybil fixture pattern

Once `sybil` is installed, `tests/contract/test_docs_fences.py` collects every `*.md` outside generated trees:

```python
# tests/contract/test_docs_fences.py
from pathlib import Path

from sybil import Sybil
from sybil.parsers.markdown import PythonCodeBlockParser, SkipParser

REPO_ROOT = Path(__file__).resolve().parents[2]

pytest_collect_file = Sybil(
    parsers=[PythonCodeBlockParser(), SkipParser()],
    patterns=["*.md"],
    path=REPO_ROOT,
    excludes=[
        "CHANGELOG.md",
        ".rulesgen-data/**",
        "~.rulesgen-data/**",
        "dist/**",
        "site/**",
        "node_modules/**",
        ".venv/**",
    ],
).pytest()
```

A fence that should NOT execute is preceded by `<!-- skip: next -->` on the line above; a range is wrapped with `<!-- skip: start -->` / `<!-- skip: end -->`. Sybil's `SkipParser` honors these directives. The skip directive's argument is parsed as a Python conditional, so the reason goes in a separate HTML comment above the skip directive (for example, `<!-- requires live OpenSandbox service -->`).

## Internal link check pattern

`tests/contract/test_docs_links.py` walks every `*.md` and asserts each relative link resolves:

```python
# tests/contract/test_docs_links.py
from __future__ import annotations

import re
from pathlib import Path

import pytest

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#?]+)(?:[#?][^)]*)?\)")
REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_NAMES = {"CHANGELOG.md"}
SKIP_PARTS = {".rulesgen-data", "~.rulesgen-data", "dist", "site", "node_modules", ".venv"}


def _md_files() -> list[Path]:
    return [
        p
        for p in REPO_ROOT.rglob("*.md")
        if p.name not in SKIP_NAMES and not (set(p.parts) & SKIP_PARTS)
    ]


@pytest.mark.parametrize("md", _md_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_internal_links_resolve(md: Path) -> None:
    text = md.read_text(encoding="utf-8")
    unresolved: list[str] = []
    for url in LINK_RE.findall(text):
        if url.startswith(("http://", "https://", "mailto:")):
            continue
        target = (md.parent / url).resolve()
        if not target.exists():
            unresolved.append(url)
    assert not unresolved, f"{md}: unresolved internal links: {unresolved}"
```

## Glossary lint pattern

`tests/contract/test_docs_glossary.py` reads `docs/agent-harness/glossary.md`, extracts every canonical term (entries surrounded by `**...**` in glossary tables), and asserts that:

1. Every `[[term]]` reference in any other doc resolves to a defined glossary term.
2. No doc uses a forbidden synonym for a canonical term (synonyms list is maintained in the glossary's §13 "Preferred wording for agents").

Align the parser to the glossary's actual table format when implementing.

## Settings / schema / route cross-check

`tests/contract/test_docs_crossref.py` extracts patterns that look like:

- Settings env-var names: `RULESGEN_*`, `LITELLM_*`, `OSS_*`, `DATABRICKS_*` — must resolve to a field in `src/rulesgen/core/config.py`.
- Schema field names referenced in HTTP / JSON fences — must resolve to a field on a Pydantic model in `src/rulesgen/schemas/`.
- Endpoint paths matching `/v1/...` — must resolve to a route registered under `src/rulesgen/api/v1/`.

Use `importlib` + Pydantic v2 introspection (`model.model_fields`) to verify; do **not** start the FastAPI app for this test.

## DSL fence test

`tests/contract/test_docs_dsl.py` walks every `*.md`, extracts ` ```dsl ` fences, and asserts each parses and validates via `rulesgen.library`. A rejected example uses ` ```dsl !rejected ` and documents the expected error class on the next line as `<!-- expects: <ExceptionClassName> -->`; the test asserts the rejection happens with that class.

## Quality gates to run

After approval and once `sybil` is installed:

```bash
# from repo root
cd "$(git rev-parse --show-toplevel)"
uv run --no-sync pytest tests/contract/test_docs_fences.py -q
uv run --no-sync pytest tests/contract/test_docs_links.py -q
uv run --no-sync pytest tests/contract/test_docs_glossary.py -q
uv run --no-sync pytest tests/contract/test_docs_crossref.py -q
uv run --no-sync pytest tests/contract/test_docs_dsl.py -q
# combined
uv run --no-sync pytest tests/contract/ -q
```

For external link checks (gated; CI nightly or on `docs/**` path):

<!-- skip: CI-only command; not safe to run from the agent harness. -->
```bash
markdown-link-check --config .markdown-link-check.json README.md docs/**/*.md
```

`.markdown-link-check.json` lives at repo root once approved. It should:

- Ignore `localhost` and developer-specific hostnames.
- Apply a small retry / timeout for flaky external hosts.
- Maintain an allow-list of stable external domains.

## When to invoke

- Before every commit that touches a file matched by `documentation-contract.md` `paths:` (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `NL-to-Python-Generation-*.md`, `Recommended Scaffold for a Uvicorn-Based Python REST API.md`, `docs/**`, `samples/**/*.md`).
- After any change to `src/rulesgen/core/config.py`, `src/rulesgen/api/v1/`, or `src/rulesgen/schemas/` — docs may now be stale.
- After any glossary edit.

## Do not

- Do not run external link checks against live LLM gateways, OpenSandbox endpoints, or customer hosts.
- Do not introduce doc tests that read from `.rulesgen-data/` or other runtime artefact paths.
- Do not start the FastAPI app for doc cross-reference tests — use `importlib` + Pydantic introspection.
- Do not add `sybil`, `lychee`, or `markdown-link-check` to `pyproject.toml`, `uv.lock`, or `.github/workflows/ci.yml` without explicit human approval per the CLAUDE.md "Approval contract".
- Do not weaken doc tests to make them pass — if a fence is wrong, fix the fence; if a claim is stale, fix the claim.

## Handoff

State:
- Which doc-test files exist (or were added) and the result of each.
- Whether external link checks ran (and how).
- Files that failed and the failure mode.
- Any glossary, Settings, schema, or route drift uncovered.
- Whether dependency approval was requested and granted.
