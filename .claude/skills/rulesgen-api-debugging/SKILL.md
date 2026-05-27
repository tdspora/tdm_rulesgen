---
name: rulesgen-api-debugging
description: Use for FastAPI route, middleware, lifespan, dependency injection, or Problem Details response issues in Rulesgen.
---

# Rulesgen API Debugging

## Workflow

1. Capture the failing request: method, path, headers (especially `X-Request-ID`, `X-API-Key`, `Authorization`, `Content-Type`), body, and full response (status, headers, body).
2. Reproduce against the app via `TestClient` in an integration test before changing production code:
   ```python
   from fastapi.testclient import TestClient
   from rulesgen.main import create_app
   client = TestClient(create_app())
   ```
3. Classify the failure:
   - **422 Unprocessable Entity** — FastAPI request validation. Schema in `rulesgen/schemas/`; verify field types and required fields.
   - **400 / domain error in Problem Details shape** — handled by `ExceptionMappingMiddleware` + handlers in `rulesgen/api/exception_handlers.py`. Trace from the raised domain exception (`rulesgen/domain/exceptions.py`) to the mapping.
   - **401 / 403** — auth resolver in `rulesgen/auth/resolver.py` + dependency in `rulesgen/api/dependencies.py`.
   - **500 with Problem Details** — unhandled exception caught by middleware. Find the underlying exception in logs (with `X-Request-ID` correlation), then add an explicit mapping if appropriate.
   - **500 without Problem Details** — middleware/handler regression. High priority; add a contract test.
   - **CORS / TrustedHost rejection** — `Settings.cors_allow_origins`, `Settings.trusted_hosts` in `rulesgen/core/config.py`. Do not hardcode `*`.
4. Confirm middleware order in `rulesgen/main.py:create_app`:
   - `ExceptionMappingMiddleware` (outermost: maps exceptions to Problem Details)
   - `RequestContextMiddleware` (request id, scoped state)
   - `TrustedHostMiddleware`
   - `CORSMiddleware` (innermost)
   Reordering changes observable behavior.
5. Validate the fix:
   - Contract test for response shape in `tests/contract/`.
   - Integration test for end-to-end behavior in `tests/integration/`.
6. Verify the error path does **not** leak stack traces, file paths, prompts, or dataset values in the Problem Details body.

## Common pitfalls

- Raising `HTTPException(detail="...")` directly — emits JSON shape that is not Problem Details. Raise a domain exception instead.
- Reading env vars directly inside a route — go through `Settings` injected via `get_settings`.
- Adding global state on `app.state` — use `RequestContextMiddleware` for request-scoped state, or `lifespan` for app-scoped state.
