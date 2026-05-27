---
paths:
  - "src/rulesgen/compiler/**"
  - "src/rulesgen/execution/**"
  - "src/rulesgen/infra/llm_gateway.py"
  - "src/rulesgen/infra/semantic_cache.py"
  - "src/rulesgen/infra/prompt_templates.py"
  - "NL-to-Python-Generation-DSL.md"
  - "NL-to-Python-Generation-Overview.md"
---

# DSL, Compiler, and LLM Rules

- The DSL contract is documented in `NL-to-Python-Generation-DSL.md` and `NL-to-Python-Generation-Overview.md`. Treat those documents as authoritative — update them in the same change that changes parser, validator, or runtime semantics.
- Compiler pipeline (`rulesgen/compiler/`):
  - `parser.py` — text → AST.
  - `types.py` — type system / inference.
  - `validator.py` — AST safety + semantic validation. **Security-critical**: do not weaken without security review.
  - `runtime_spec.py` — validated AST → `RuntimeSpec` executed by the engine.
  - `service.py` — orchestrates parse → validate → spec.
- Every change to parser / validator / runtime spec must include:
  - A positive test in `tests/unit/test_compiler.py` for the new accepted form.
  - A negative test confirming previously accepted forms still parse and previously rejected forms still reject.
  - A `RuntimeSpec` snapshot/shape assertion when the spec format changes.
- Execution engines (`rulesgen/execution/`) consume `RuntimeSpec` only; do not let the engine see un-validated input.
- LLM gateway (`rulesgen/infra/llm_gateway.py`) uses `litellm`:
  - Endpoint, model, and credentials come from `Settings`; do not hardcode.
  - Tests must mock at the gateway client boundary — never hit a live LLM in CI.
- Semantic cache (`rulesgen/infra/semantic_cache.py`) uses `gptcache`:
  - Cache keys must hash sensitive input; do not store raw customer data.
  - Cache backend URI is an environment variable name.
- Prompt templates (`rulesgen/infra/prompt_templates.py`) are part of the LLM contract — changes that alter output schema require regenerating fixtures and updating tests.
