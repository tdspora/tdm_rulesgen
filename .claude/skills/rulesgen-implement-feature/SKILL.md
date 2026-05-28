---
name: rulesgen-implement-feature
description: Use for implementing production-grade Rulesgen features or non-trivial code changes.
---

# Rulesgen Feature Implementation

## Vocabulary

Use the names defined in `docs/agent-harness/glossary.md` — the single authoritative dictionary for both business and technical vocabulary. If a draft uses an undefined term, add it to the glossary in the same change rather than inventing a synonym.

## Workflow

0. **Bootstrap check.** If you just pulled `main`, switched branches, or any subsequent `uv run …` produces `ModuleNotFoundError`, invoke the `rulesgen-bootstrap` skill before continuing.
1. **Frame the change.** Restate the requested change and identify affected layers: library API (`rulesgen.library`), HTTP API (`rulesgen/api/v1/`), compiler, execution backend, services, infra (LLM gateway, semantic cache, OSSFS), auth, middleware, schemas, DSL contract.
2. **Research.** Use the `rulesgen-codebase-researcher` agent (or targeted `grep`/`Read`) to locate the relevant files, schemas, and existing tests.
3. **Read the contract.** If the change touches parser, validator, or runtime semantics, read `requirements/NL-to-Python-Generation-DSL.md` and `requirements/NL-to-Python-Generation-Overview.md` in full.
4. **Plan.** Produce a concise plan listing: files to touch, schemas/models to add or update, tests to add (`tests/unit/`, plus `tests/contract/` or `tests/integration/` if applicable), and any backward-compatibility risk (per the glossary definition of [[backward compatibility]]).
5. **Implement.** Smallest viable change. Follow `python-quality.md` and `project-architecture.md`.
6. **Test** per `testing-contract.md`:
   - Unit test for every new branch / parser path / validator rule / service method.
   - Contract test for any change to API error or Problem Details shape.
   - Integration test for any change to FastAPI routing, lifespan, or middleware.
7. **Validate locally**, all from the repo root (`cd "$(git rev-parse --show-toplevel)"`):
   ```bash
   uv run --no-sync pytest tests/unit/test_<target>.py -q
   uv run --no-sync ruff check <touched paths>
   uv run --no-sync ruff format --check <touched paths>
   uv run --no-sync mypy src
   uv run --no-sync pytest -q          # full suite before handoff
   ```
   The `--no-sync` form is preferred because the harness denies bare `uv sync`; if `--no-sync` reports a missing module, run `rulesgen-bootstrap`.
8. **Lockfile.** If dependencies changed, `uv lock --check` must pass and `pyproject.toml` + `uv.lock` must be committed together. Adding/removing a dependency is an escalation (see CLAUDE.md "Escalation triggers" + "Approval contract").
9. **Commit.** Use Conventional Commit messages — `semantic-release` derives versions from them. Mark breaking changes explicitly with `!` and a `BREAKING CHANGE:` footer.
10. **Handoff.** State: changed files, tests run, lint/mypy results, dependency updates, residual risk, documentation updated (DSL docs, README, sample rules, glossary).

## Escalate before proceeding when

- The change weakens compiler validator or sandbox isolation.
- The change adds, removes, or upgrades a runtime dependency.
- The change touches `pyproject.toml:project.version`, `[tool.semantic_release]`, the release CI job, or `secrets.DEPLOY_KEY` handling.
- The change alters LLM gateway endpoint, credentials, or prompt template output schema.
- The change relaxes an auth backend or middleware security setting.
