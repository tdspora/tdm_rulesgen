---
name: rulesgen-bootstrap
description: Use to verify or set up the local Rulesgen development environment (uv venv + all extras synced from the lockfile). Run this if any subsequent command fails with `ModuleNotFoundError`, `command not found`, or "no such tool installed", or before running quality gates on a fresh checkout.
---

# Rulesgen Bootstrap

## Purpose

Guarantee that the local `.venv` matches `uv.lock` exactly and has every extra the harness expects.

The harness assumes the following are importable in the project venv:

- `pytest`, `hypothesis` — testing
- `ruff`, `mypy`, `pip-audit` — quality gates
- `litellm`, `gptcache` — runtime (LLM gateway + semantic cache)
- `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings` — API + config
- `hatchling`, `python-semantic-release` (CI only)

On a fresh checkout or after a `pyproject.toml` / `uv.lock` change, one of those will be missing and silent failures follow.

## Workflow

1. Resolve repo root:
   ```bash
   REPO_ROOT="$(git rev-parse --show-toplevel)"
   cd "${REPO_ROOT}"
   ```
2. Check current venv against lockfile (must already be in sync; no mutation):
   ```bash
   uv lock --check
   ```
   - If this exits non-zero, the lockfile is drifted. Stop and invoke `rulesgen-ci-triage`.
3. Sync with all expected extras, locked (no upgrade allowed):
   ```bash
   uv sync --extra api --extra dev --locked
   ```
   - `--locked` guarantees no version drift.
   - Without `--extra api` / `--extra dev` the API and dev tools (mypy, ruff, pip-audit) are not installed.
4. Verify the critical imports resolve in the project venv:
   ```bash
   uv run --no-sync python -c "import pytest, ruff, mypy, litellm, gptcache, fastapi, pydantic, pydantic_settings; print('bootstrap OK')"
   ```
   - On `ModuleNotFoundError`, the matching extra is missing from `pyproject.toml`; this is an escalation to `rulesgen-release-engineer`.
5. Verify the application factory loads:
   ```bash
   uv run --no-sync python -c "from rulesgen.main import create_app; create_app(); print('create_app OK')"
   ```
   - If this fails, the most likely cause is a missing env var; check `.env*` against `rulesgen/core/config.py` settings.
6. Confirm the cache directories are absent or empty (no committed runtime state):
   ```bash
   ls -d "${REPO_ROOT}/.rulesgen-data" "${REPO_ROOT}/~.rulesgen-data" 2>/dev/null | head
   ```

## When to invoke

- Fresh `git clone` or new branch checkout that touched `pyproject.toml` / `uv.lock`.
- `uv run …` reports `ModuleNotFoundError` for `litellm`, `gptcache`, `pydantic_settings`, `fastapi`, etc.
- Before running `rulesgen-release-check`, `rulesgen-implement-feature`, or any skill that runs the test suite.
- After a `git pull` on `main` when CI just ran successfully but local commands suddenly fail.

## Do not

- Do not run `uv sync` without `--locked` (denied by `.claude/settings.json`; would mutate the lockfile silently).
- Do not run `uv sync --upgrade*` (denied) — that's a dependency change, which is an escalation.
- Do not `pip install` packages outside the lockfile.

## Handoff

State:

- Whether `uv lock --check` passed.
- Which extras were installed.
- Whether all critical imports resolved.
- Whether `create_app()` returned an app instance.
