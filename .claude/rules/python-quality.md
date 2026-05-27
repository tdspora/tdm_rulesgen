---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Python Quality Rules

- Follow existing style and module boundaries in `rulesgen`.
- `ruff` (lint + format) and `mypy --strict` are enforced in CI — both must pass for every change.
  - Ruff selectors: `E`, `F`, `I`, `B`, `UP` (`pyproject.toml [tool.ruff.lint]`).
  - Line length: 100. Target version: `py311`.
  - Mypy is in strict mode with `disallow_any_generics`, `no_implicit_reexport`, `warn_unused_configs`.
- Use `from __future__ import annotations` at the top of new modules to match existing style.
- Prefer Pydantic v2 models for all validated I/O; do not introduce parallel validation systems.
- Settings come from `rulesgen.core.config.Settings` via `pydantic-settings` — do not read env vars ad hoc.
- Errors:
  - Domain errors live in `rulesgen/domain/exceptions.py` and `rulesgen/core/errors.py`.
  - API errors must surface as RFC 7807 Problem Details (`rulesgen/core/problem_details.py`, `rulesgen/api/problem_details.py`). Do not raise raw `HTTPException` with arbitrary strings.
- Logging uses the configured logger from `rulesgen/core/logging.py` — never `print`, never log raw payloads.
- Async vs sync: respect each module's existing convention. FastAPI handlers and services are typically async; the compiler and validator are typically sync.
- Keep functions focused and testable; no hidden global state.
- Do not swallow exceptions without preserving diagnostic context (chain with `raise ... from exc`).
- Add type hints for every new public function, method, and return type — mypy strict requires them.
- Do not introduce new runtime dependencies without explicit approval; coordinate `pyproject.toml` and `uv.lock` updates with the change.
- Run targeted `uv run pytest` before broader validation.
