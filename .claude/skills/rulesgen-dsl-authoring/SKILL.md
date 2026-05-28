---
name: rulesgen-dsl-authoring
description: Use for authoring, reviewing, or correcting natural-language → Python generation DSL rules for Rulesgen.
---

# Rulesgen DSL Authoring

## Source of truth

- `requirements/NL-to-Python-Generation-DSL.md` — formal grammar and accepted forms.
- `requirements/NL-to-Python-Generation-Overview.md` — intent, motivating examples, expected pipeline behavior.
- `src/rulesgen/compiler/parser.py` and `src/rulesgen/compiler/validator.py` — actual accepted forms (treat as authoritative when docs disagree, and file a docs fix).
- `samples/` — committed example rules.

## Workflow

1. Identify the target column(s), input data shape, and whether the rule is deterministic or LLM-assisted.
2. Draft the rule using only accepted DSL constructs. Avoid:
   - Free imports.
   - Attribute access on builtins.
   - Dunder methods.
   - Network or filesystem I/O.
   The AST validator will reject these — and rightly so.
3. Compile and validate locally via `rulesgen.library` (or `uv run pytest`-based fixtures) before sending to the LLM gateway.
4. For LLM-assisted rules, verify:
   - Prompt template (`src/rulesgen/infra/prompt_templates.py`) handles the rule type.
   - The LLM endpoint is configured via env var, not hardcoded.
   - The semantic cache key derivation hashes any sensitive input.
5. Never embed:
   - Real customer data.
   - Real credentials.
   - Real LLM endpoint URLs.
   in committed sample rules, prompts, or test fixtures.
6. Add a unit test in `tests/unit/test_compiler.py` (positive + negative) for any new DSL construct.

## Review checklist

- The rule parses with the current parser.
- The rule passes the validator (or is correctly rejected with a clear Problem Details response).
- The `RuntimeSpec` shape matches the documented invariants.
- The rule produces deterministic output on the local execution backend given the same input + seed.
- Sample data is small, synthetic, and committable.
