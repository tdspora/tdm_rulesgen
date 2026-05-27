---
name: rulesgen-validation-debugging
description: Use for Pydantic v2 validation errors, DSL parser/validator rejections, and API request validation issues in Rulesgen.
---

# Rulesgen Validation Debugging

## Workflow

1. Capture the exact failing input (request body, DSL text, or library call) and the full error message.
2. Classify the failure:
   - **Pydantic schema** — `ValidationError` raised in `rulesgen/schemas/*` or `rulesgen/domain/models.py`. Locate the offending field via the error `loc` tuple.
   - **DSL parser** — failure in `rulesgen/compiler/parser.py`. Reproduce with a minimal DSL snippet and a unit test in `tests/unit/test_compiler.py`.
   - **DSL validator** — AST rejected by `rulesgen/compiler/validator.py`. Check whether the rejection is expected for safety; if so, document why; if not, narrow the validator rule.
   - **Runtime properties** — type or shape mismatch in `RuntimeSpec`. Check `rulesgen/compiler/runtime_spec.py` and `tests/unit/test_runtime_properties.py`.
   - **API request validation** — FastAPI rejected the request before the route. Look at the route signature, the dependency in `rulesgen/api/dependencies.py`, and the schema in `rulesgen/schemas/`.
3. Confirm the contract:
   - For schema changes: are positive **and** negative tests present?
   - For DSL changes: does `NL-to-Python-Generation-DSL.md` describe this form?
   - For API changes: does the error surface as RFC 7807 Problem Details (`tests/contract/`)?
4. Write or update a failing test that reproduces the bug before changing production code.
5. Fix in the smallest scope: schema field, validator branch, or parser rule.
6. Confirm by running `uv run pytest <targeted>` and the existing tests in the same file (no regressions).
7. Verify error response shape for API paths via `tests/contract/test_problem_details.py` patterns.

## Common pitfalls

- Loosening the AST validator to accept user input is a security issue — escalate to `rulesgen-security-reviewer`.
- Pydantic v2 default factories vs `default=` semantics differ from v1; verify against the v2 docs (use the `context7` MCP if needed).
- `from __future__ import annotations` + Pydantic v2 requires explicit `model_rebuild()` in some forward-reference cases.
