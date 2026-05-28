---
name: rulesgen-docs-authoring
description: Use for authoring or updating Rulesgen documentation — public docs (`docs/public/`), repo-root design docs, contributor docs, sample READMEs, and the glossary. Produces testable, glossary-aligned, link-integral docs.
---

# Rulesgen Docs Authoring

## Vocabulary

Use the names defined in `docs/agent-harness/glossary.md` — the single authoritative dictionary for both business and technical vocabulary. If a draft uses an undefined term, add it to the glossary in the **same change** rather than inventing a synonym. Cross-link with `[[term]]`.

## Scope

| Audience | Path |
|---|---|
| Operator / first-time user | `docs/public/` |
| Contributor (internal) | `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` |
| Designer / reviewer | `NL-to-Python-Generation-DSL.md`, `NL-to-Python-Generation-Overview.md`, `Recommended Scaffold for a Uvicorn-Based Python REST API.md` |
| Glossary (canonical) | `docs/agent-harness/glossary.md` |
| Sample-rule consumer | `samples/**/*.md` |
| Library consumer | docstrings on `src/rulesgen/library.py`, `src/rulesgen/__init__.py` |

`CHANGELOG.md` is owned by `python-semantic-release`. Do not edit. `pyproject.toml:project.version` and the release CI job are likewise off-limits.

## Workflow

1. **Frame the change.** State the audience, the change needed, and the docs affected. If a code change ships in the same PR, list the production-code files too.
2. **Locate the canonical vocab.** Read `docs/agent-harness/glossary.md` for every domain term you plan to use. If a needed term is missing, draft the glossary entry first.
3. **Cross-check claims against source.** For each substantive claim, locate the supporting file under `src/rulesgen/`:
   - Settings field → `src/rulesgen/core/config.py`
   - Endpoint / route → `src/rulesgen/api/v1/`
   - Request / response schema → `src/rulesgen/schemas/`
   - DSL construct → `src/rulesgen/compiler/parser.py` and `src/rulesgen/compiler/validator.py`
   - Problem Details shape → `src/rulesgen/core/problem_details.py`
   - Runtime helper → glossary §6 plus `src/rulesgen/compiler/types.py` / `src/rulesgen/execution/`
4. **Write testable code fences.** Each fence declares its test mode:
   - ` ```python ` — executed under `sybil`. Use the project venv, no filesystem side effects outside `tmp_path`, no live LLM calls, no live sandbox calls.
   - ` ```bash ` / ` ```sh ` — followed by an output block, OR preceded by `<!-- skip: next -->` (sybil directive). Document the reason in a separate HTML comment above the skip directive, e.g. `<!-- requires live OpenSandbox service -->`.
   - ` ```http ` / ` ```json ` — mirror a Pydantic schema or Problem Details body. Reference the schema file path in a one-line comment above the fence.
   - ` ```dsl ` — must parse and validate via `rulesgen.library`. Rejected examples use ` ```dsl !rejected ` and document the expected error class on the next line.
5. **Resolve links.**
   - Internal: relative paths from the doc to the target file or anchor. Verify each by `Read`-ing the target.
   - External: HTTPS only, no session-bound URLs. Prefer the project's GitHub repository (`https://github.com/tdspora/tdm_rulesgen/...`) over copies.
6. **Run the `rulesgen-docs-testing` skill** to validate fences, links, glossary alignment, and Settings / schema / route cross-references.
7. **Hand off to `rulesgen-docs-reviewer`** for review.
8. **Commit** with `docs:` Conventional Commit (or bundle into the production-code commit if the docs ship together).

## Glossary changes

Glossary edits are higher-stakes because every other doc references the glossary:

1. **Adding a term**: write the entry, cross-link related terms with `[[other-term]]`, and cite the source file under `src/rulesgen/` if the term is technical or runtime.
2. **Changing a definition**: `grep -r '\[\[<term>\]\]' docs/ samples/ README.md NL-to-Python-Generation-*.md CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md` to find every dependent reference; update all of them in the same change.
3. **Removing a term**: confirm zero references across docs and code before removal.

## Sample-rule docs

Sample READMEs in `samples/` must:

- Include a parseable DSL snippet that the compiler accepts.
- Reference the dataset by relative path inside `samples/`.
- Use only synthetic, committable data — never real customer rows.
- Never embed real LLM endpoints or real credentials.

## Escalate before proceeding when

- The change adds a doc-test runtime or dev dependency (`sybil`, `lychee`, `markdown-link-check`, …). Print `APPROVAL REQUIRED: ...` per the CLAUDE.md "Approval contract" and wait for `approved`.
- The change weakens a compiler, sandbox, auth, or LLM-egress safety claim in any doc. Escalate to `rulesgen-security-reviewer`.
- The change touches `CHANGELOG.md`, `pyproject.toml:project.version`, or the release CI job.
- A new term is contested by two or more reviewers — glossary disputes are an architectural concern. Bring in `rulesgen-architect`.

## Do not

- Do not invent new vocabulary; extend the glossary.
- Do not weaken safety claims documented in `NL-to-Python-Generation-DSL.md`, `NL-to-Python-Generation-Overview.md`, or `SECURITY.md`.
- Do not paste real endpoints, real credentials, real customer data, or developer-specific configuration.
- Do not edit `CHANGELOG.md`, `pyproject.toml:project.version`, or the release CI job.

## Handoff

State:
- Files changed.
- Audience.
- Glossary entries added or updated.
- Code fences added and their test mode.
- Internal versus external links added.
- Which `rulesgen-docs-testing` checks were run and the results.
- Whether `rulesgen-docs-reviewer` has reviewed.
- Residual risk.
