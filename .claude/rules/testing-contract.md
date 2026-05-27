# Testing Contract

Every production-code change requires tests unless the change is documentation-only.

## Minimum expectations

- **Bug fix**: regression test proving the bug is fixed.
- **Pydantic schema change**: positive and negative validation tests in `tests/unit/`.
- **Compiler / parser / validator change**: targeted unit tests covering accepted forms, rejected forms, and `RuntimeSpec` shape.
- **Execution engine change**: unit tests against the relevant backend (`local`, `opensandbox`, `alibaba_opensandbox`) using existing fixtures in `tests/conftest.py`.
- **FastAPI route change**: unit test for the service plus an integration test in `tests/integration/` exercising the route through the app.
- **API error / Problem Details change**: contract test in `tests/contract/` (see `test_problem_details.py` for the pattern).
- **LLM gateway change**: unit test with the gateway client mocked at the boundary; do not hit live LLM endpoints from tests.
- **Auth backend change**: unit tests for both `authenticated` and `rejected` paths; treat as medium-to-high risk.
- **Packaging change**: `uv build` must succeed and produce a wheel that imports cleanly.
- **Runtime / sandbox behavior change**: targeted unit tests first; only run end-to-end OpenSandbox flows when justified and the local service is available.

## Test locations

- Unit: `tests/unit/`
- Integration: `tests/integration/` (exercises the FastAPI app via `TestClient` / lifespan).
- Contract: `tests/contract/` (RFC 7807 / Problem Details response shape).
- Shared fixtures: `tests/conftest.py`.
- `hypothesis` is available and appropriate for parser / validator / schema invariants — use it sparingly for high-value properties.

## Commands

- Targeted: `uv run pytest tests/unit/test_<target>.py -q`
- All unit: `uv run pytest tests/unit/`
- Full suite: `uv run pytest`
- Lint + format: `uv run ruff check . && uv run ruff format --check .`
- Type check: `uv run mypy src` (strict mode is enforced).

## Final handoff must state

- Tests run.
- Tests not run and reason.
- Lint / format / mypy results.
- Generated artifacts (if any).
- Residual risk.
