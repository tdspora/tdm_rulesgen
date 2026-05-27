---
name: rulesgen-ci-triage
description: Use for GitHub Actions CI failures (ruff, mypy, pytest, uv build, pip-audit, semantic-release) in Rulesgen.
---

# Rulesgen CI Triage

## Workflow

1. Classify the failure by step in `.github/workflows/ci.yml`:
   - `uv sync --extra api --extra dev --locked` → lockfile drift, dependency resolution.
   - `uv run ruff check .` / `uv run ruff format --check .` → lint or formatting.
   - `uv run mypy src` → strict typing.
   - `uv run pytest` → unit / integration / contract test failure.
   - `uv build` → packaging.
   - `uv run pip-audit` → vulnerability finding (non-blocking, `continue-on-error: true`, but triage anyway).
   - `release` job → `python-semantic-release` failure (escalate, do not retry blindly).
2. Reproduce locally with the **same** command CI runs. Do not invent variants.
3. Lockfile drift:
   - `pyproject.toml` changed but `uv.lock` did not (or vice versa).
   - Diagnose locally: `uv lock --check`. The harness denies bare `uv lock` (would mutate the lockfile without review).
   - Fix is an **escalation**: state `APPROVAL REQUIRED: regenerate uv.lock for <change description>` and wait for `approved` per CLAUDE.md "Approval contract". After approval, run `uv lock` then commit both files.
4. Lint / format:
   - Fix with `uv run ruff check . --fix` and `uv run ruff format .` for safe auto-fixes.
   - Re-run the check command exactly.
5. Mypy strict failures:
   - Add explicit type hints — strict mode disallows untyped defs and `Any` generics.
   - Do not add `# type: ignore` without a comment naming the specific reason.
6. Pytest failures:
   - Run the single failing test: `uv run pytest tests/<path>::<test> -q -x`.
   - For flaky LLM/sandbox tests, confirm the mock at the gateway boundary is intact — never make the test hit live services.
7. `uv build` failures:
   - Usually a hatchling config issue in `pyproject.toml` or a missing `src/rulesgen/__init__.py` field.
8. `pip-audit` findings:
   - Identify package + advisory.
   - For HIGH/CRITICAL: propose a version bump via `uv add 'pkg>=X.Y'` and update `uv.lock`.
   - For others: track and decide alongside release manager.

## Do not

- Do not push to `main` to "see if CI passes."
- Do not retrigger the `release` job manually.
- Do not bypass `--locked` by deleting `uv.lock`.
- Do not run bare `uv lock` or `uv sync` — both denied by the harness for safety. Use `uv lock --check` and `uv sync --locked` (or escalate).
- Do not skip hooks (`--no-verify`) — `.pre-commit-config.yaml` mirrors CI.
