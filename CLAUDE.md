# Rulesgen Claude Code Operating Context

## Project facts

- `tdm_rulesgen` is a library + FastAPI service for safe natural-language → Python rule generation and execution over tabular data.
- Package root: `src/rulesgen`. Distributed as the `rulesgen` wheel (hatchling build backend).
- Supported Python versions: 3.11 and 3.12 (`requires-python = ">=3.11"`).
- Toolchain: `uv` (lockfile `uv.lock`, `uv sync --extra api --extra dev --locked`), `ruff` (lint + format), `mypy --strict`, `pytest`, `hypothesis`.
- Primary workflows:
  - **Library API** (`rulesgen.library`) — programmatic rule compilation and generation.
  - **FastAPI app** (`rulesgen.main:app`, optional `[api]` extra) — REST endpoints for datasets, jobs, rules, health.
  - **Compiler** (`rulesgen/compiler/`) — parses and validates the NL-to-Python Generation DSL into a `RuntimeSpec`.
  - **Execution backends** (`rulesgen/execution/`) — local Python execution and OpenSandbox / Alibaba OpenSandbox isolated execution.
  - **LLM gateway** (`rulesgen/infra/llm_gateway.py`) — `litellm` + `gptcache` semantic cache for NL→DSL synthesis.
- Reference docs: `requirements/NL-to-Python-Generation-DSL.md`, `requirements/NL-to-Python-Generation-Overview.md`, and repo-root `Recommended Scaffold for a Uvicorn-Based Python REST API.md`.
- Schema/validation is **Pydantic v2** (`rulesgen/schemas/`, `rulesgen/domain/models.py`); error responses follow RFC 7807 Problem Details (`rulesgen/api/problem_details.py`, `tests/contract/test_problem_details.py`).
- Auth: pluggable backends in `rulesgen/auth/backends/`, resolver in `rulesgen/auth/resolver.py`.
- Tests live in `tests/unit/`, `tests/integration/`, `tests/contract/`. `pythonpath = ["src"]` is set in `pyproject.toml`.
- CI: GitHub Actions (`.github/workflows/ci.yml`) — ruff, mypy, pytest, `uv build`, `pip-audit`, `python-semantic-release` on `main`.
- Versioning: `python-semantic-release` driven by Conventional Commits. `pyproject.toml:project.version` is the source of truth — do not hand-edit.
- Containers: `Dockerfile`, `compose.yaml`, `compose.opensandbox.yaml`.
- Generated/runtime outputs (`.rulesgen-data/`, `dist/`, `site/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`) are not source assets.

## Engineering standards

- Implement production code only with corresponding tests.
- Prefer minimal, isolated changes over broad rewrites.
- Preserve public library API (`rulesgen.library`), HTTP API contracts, and CLI/SDK backward compatibility unless the task explicitly requires a breaking change.
- Follow Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`, breaking marker `!`) — `python-semantic-release` derives versions from commit history.
- Pass `ruff check`, `ruff format --check`, and `mypy --strict` for any code change.
- Honor existing module boundaries: `compiler/`, `execution/`, `services/`, `api/`, `domain/`, `infra/`, `auth/`, `schemas/`, `core/`, `middleware/`.
- Add unit tests for any new branch, parser path, validator rule, or service method.
- Add contract tests for any change to API error responses or Problem Details payloads.
- Add integration tests for any change to FastAPI routing, dependency injection, lifespan, or middleware behavior.
- Do not add new runtime dependencies without explicit approval; coordinate `uv.lock` updates with the change.

## Security standards

- Never commit secrets, LLM gateway keys, OpenSandbox endpoints/keys, OSS access keys, deploy keys, or GitHub tokens.
- Treat all credential fields (LLM provider keys, `LITELLM_*`, OpenSandbox / Alibaba OSS keys, semantic cache backends, GitHub `DEPLOY_KEY`) as environment variable names — never literal values.
- Do not inspect `.env`, `.env.*`, `~.env`, `.cursor/mcp.json`, or developer-specific settings unless explicitly authorized.
- Keep `.rulesgen-data/`, `~.rulesgen-data/`, `dist/`, `site/`, and generated samples out of source control.
- The compiler / executor enforces a safe Python subset; never weaken the AST validator (`rulesgen/compiler/validator.py`) or sandbox isolation (`rulesgen/execution/`) without security review.
- LLM egress is only permitted to customer-approved gateway endpoints — never hardcode endpoint URLs in code, tests, or sample DSL.
- Logs must not contain raw dataset rows, generated samples, prompts, or LLM responses at any level.

## Default implementation workflow

1. Inspect relevant source, tests, DSL reference docs (`requirements/NL-to-Python-Generation-*.md`), and CI definition (`.github/workflows/ci.yml`).
2. Produce a concise implementation plan.
3. Implement the smallest viable change.
4. Add or update unit tests (`tests/unit/`).
5. Add contract tests (`tests/contract/`) for API error/response shape changes; add integration tests (`tests/integration/`) for routing, lifespan, or end-to-end flow changes.
6. Run the smallest relevant validation first: `uv run pytest tests/unit/test_<target>.py` then `uv run ruff check <paths>` and `uv run mypy src`.
7. Escalate to broader CI-style checks (`uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy src`, `uv build`) before final handoff.
8. Report changed files, tests run, results, and residual risks.

## Canonical vocabulary

- All project vocabulary — business, technical, runtime — lives in a single file: `docs/agent-harness/glossary.md`.
- When a new term appears anywhere in this repository (PRDs, JIRA, design docs, code, DSL, prompts), add it to the glossary in the same change. Cross-link with `[[term]]`; do not re-define.

## Approval contract

Anything an agent is told to "request human approval for" must follow this contract:

1. The agent prints a single line: `APPROVAL REQUIRED: <one-sentence summary of the action>`.
2. The agent stops and yields the turn to the human.
3. The human authorizes by typing exactly one of:
   - `approved` — proceed exactly as proposed.
   - `approved: <free-text constraint>` — proceed, but apply the constraint.
   - `deny` — abort and explain the reason in a brief follow-up.
4. Any other response (silence, `ok`, thumbs-up, emoji, paraphrase) is **not** approval. The agent must re-ask.

This contract applies to every escalation trigger below, every `ask` permission, and every `rulesgen-harness-update` action.

## Escalation triggers (require human approval)

- Any release workflow change (`.github/workflows/ci.yml` release job, `pyproject.toml [tool.semantic_release]`, `CHANGELOG.md` formatting).
- Manual version bumps in `pyproject.toml:project.version` (semantic-release owns this).
- Compiler/executor safety relaxations (AST validator, sandbox runner, opensandbox backends).
- LLM gateway credential, endpoint, or prompt template changes that affect egress.
- Auth backend, dependency, or middleware changes that affect authentication or trust boundaries.
- Docker image or `compose.*.yaml` changes that alter runtime topology.
- Adding or removing runtime dependencies in `pyproject.toml`.
- Any operation involving secrets, private data, or `.env*` files.
