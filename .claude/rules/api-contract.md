---
paths:
  - "src/rulesgen/api/**"
  - "src/rulesgen/main.py"
  - "src/rulesgen/middleware/**"
  - "src/rulesgen/schemas/**"
  - "src/rulesgen/core/problem_details.py"
  - "tests/contract/**"
  - "tests/integration/**"
---

# FastAPI Contract Rules

- The HTTP API is a public contract. Backward-incompatible changes to request bodies, response bodies, status codes, headers, or error shape require a Conventional Commit breaking marker (`!:` or `BREAKING CHANGE:`).
- Version new endpoints under `rulesgen/api/v1/` (a new major would mount alongside, e.g. `v2/`); do not break existing v1 routes.
- All error responses must be RFC 7807 **Problem Details** JSON (`application/problem+json`). Use the helpers in `rulesgen/core/problem_details.py` and `rulesgen/api/problem_details.py`; do not raise bare `HTTPException(detail="...")` with arbitrary strings.
- Request/response models are Pydantic v2, defined in `rulesgen/schemas/`. Reuse `schemas/common.py` primitives before adding new ones.
- Exception flow:
  - Domain code raises domain exceptions (`rulesgen/domain/exceptions.py`).
  - `ExceptionMappingMiddleware` and `install_exception_handlers` map them to Problem Details.
  - Do not catch-and-rewrap exceptions at the route layer unless you are adding a new mapping.
- Middleware order in `main.py:create_app` is intentional (exception mapping → request context → trusted host → CORS). Do not reorder without justification and tests.
- CORS / TrustedHost / docs exposure are configured via `Settings`. Do not hardcode `allow_origins=["*"]` or `allowed_hosts=["*"]` in code.
- Add a contract test in `tests/contract/` for every change to error response shape; add an integration test in `tests/integration/` for every new route or routing-affecting change.
- Auth is applied via `rulesgen/api/dependencies.py` and resolved through `rulesgen/auth/resolver.py`; do not bypass it on a per-route basis without explicit approval.
