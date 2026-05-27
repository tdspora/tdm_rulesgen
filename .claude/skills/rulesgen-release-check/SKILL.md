---
name: rulesgen-release-check
description: Use for release readiness, packaging, versioning, wheel, or dependency validation in Rulesgen.
---

# Rulesgen Release Check

## Workflow

1. Confirm versioning source: `pyproject.toml:project.version` is owned by `python-semantic-release`. Verify nobody hand-edited it on the release branch.
2. Confirm commit history on the release branch uses Conventional Commits and produces the intended bump (`feat:` → minor, `fix:` → patch, `!` / `BREAKING CHANGE:` → major; with `major_on_zero = false` and `allow_zero_version = true` while we're on 0.x).
3. Confirm `uv.lock` is in sync: `uv lock --check`.
4. Build artifacts: `uv build` — should produce both `dist/rulesgen-<version>-py3-none-any.whl` and `dist/rulesgen-<version>.tar.gz`.
5. Inspect wheel contents: `uv run --no-sync python -m zipfile -l dist/rulesgen-*.whl` — confirm no `.env`, `.rulesgen-data/`, `~.rulesgen-data/`, developer config, or secrets are packaged. Use `uv run` so inspection runs in the project venv, not the system Python.
6. Quality gates (mirror CI). Run from the repo root: `cd "$(git rev-parse --show-toplevel)"`. Prefer `--no-sync` so the venv state is what CI will see:
   - `uv run --no-sync ruff check .`
   - `uv run --no-sync ruff format --check .`
   - `uv run --no-sync mypy src`
   - `uv run --no-sync pytest`
   - `uv run --no-sync pip-audit --skip-editable` (triage HIGH/CRITICAL).
   If any quality gate fails with `ModuleNotFoundError`, invoke `rulesgen-bootstrap` once and retry.
7. Confirm `.github/workflows/ci.yml` release job is unchanged outside approved scope. The `release` job:
   - Runs only on `main` / `master`.
   - Requires `secrets.DEPLOY_KEY` SSH push.
   - Uses `python-semantic-release@v10.2.0`.
   - Requires a baseline `v*` tag.
8. Confirm `CHANGELOG.md` updates only via semantic-release.
9. Confirm Docker / compose changes are out of scope for the release (or escalated).

## Output

A go/no-go checklist with each item marked pass/fail and evidence.

## Escalate to a human for

- Any change to the `release` job, `DEPLOY_KEY` usage, or `[tool.semantic_release]` config.
- Manual version edits in `pyproject.toml`.
- Manual changelog edits.
- `uv publish` from any non-CI environment.
