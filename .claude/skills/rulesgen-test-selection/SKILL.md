---
name: rulesgen-test-selection
description: Use for selecting the correct test, lint, type-check, or packaging command for a given Rulesgen change.
---

# Rulesgen Test Selection

## Fast path decision tree

| Change type | Command(s) |
|---|---|
| Pure docs (`README.md`, `NL-to-Python-*.md`, `docs/`) | `uv run ruff check .` (skip pytest) |
| Pydantic schema (`src/rulesgen/schemas/**`, `domain/models.py`) | `uv run pytest tests/unit/test_<schema>.py`, then `uv run mypy src` |
| Compiler / parser / validator (`src/rulesgen/compiler/**`) | `uv run pytest tests/unit/test_compiler.py tests/unit/test_runtime_properties.py` |
| Execution backend (`src/rulesgen/execution/**`) | `uv run pytest tests/unit/test_opensandbox_runner.py tests/unit/test_opensandbox_backends.py tests/unit/test_generation_engine.py` |
| LLM gateway / cache (`src/rulesgen/infra/**`) | `uv run pytest tests/unit/test_llm_gateway.py` |
| Services (`src/rulesgen/services/**`) | `uv run pytest tests/unit/test_<service>_service.py` |
| FastAPI route (`src/rulesgen/api/**`, `main.py`) | `uv run pytest tests/integration/test_api_flow.py tests/contract/test_problem_details.py` |
| Middleware (`src/rulesgen/middleware/**`) | `uv run pytest tests/integration/ tests/contract/` |
| Settings (`src/rulesgen/core/config.py`) | `uv run pytest tests/unit/test_settings.py` |
| Library API (`src/rulesgen/library.py`) | `uv run pytest tests/unit/test_library_api.py` |
| Auth (`src/rulesgen/auth/**`) | Add targeted unit tests; treat as medium-high risk |
| Packaging (`pyproject.toml`, `uv.lock`) | `uv lock --check && uv build` |
| CI (`.github/workflows/**`) | High-risk; escalate before changing |

## Always before handoff

1. Targeted pytest above.
2. `uv run ruff check <touched paths>` and `uv run ruff format --check <touched paths>`.
3. `uv run mypy src`.
4. `uv run pytest` (full suite) before opening a PR.

## When in doubt

Run the full suite: `uv run pytest`. It's fast enough that "I'm not sure which tests to run" is not a good reason to skip.
