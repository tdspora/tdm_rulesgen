# NL-to-Python Generation DSL Requirements

This document describes the DSL that is implemented today. It is not a survey of possible parsers, helper libraries, or future syntax. The current contract is a restricted Python expression subset parsed with `ast.parse(..., mode="eval")`, validated by a whitelist, compiled from a validated AST, and executed with restricted runtime locals.

For source-of-truth implementation details, see:

- [parser.py](../src/rulesgen/compiler/parser.py)
- [validator.py](../src/rulesgen/compiler/validator.py)
- [service.py](../src/rulesgen/compiler/service.py)
- [runtime_spec.py](../src/rulesgen/compiler/runtime_spec.py)
- [engine.py](../src/rulesgen/execution/engine.py)
- [test_compiler.py](../tests/unit/test_compiler.py)
- [test_api_flow.py](../tests/integration/test_api_flow.py)

## Implemented DSL Surface

The DSL is one Python expression. It is not a statement language and does not support imports, assignments, function definitions, loops, comprehensions, attribute access, subscripting, or arbitrary builtins.

Accepted syntax is the subset admitted by [DSLValidator](../src/rulesgen/compiler/validator.py):

- Literals through `ast.Constant`.
- Calls to whitelisted runtime helpers only.
- Arithmetic operators: addition, subtraction, multiplication, division, and modulo.
- Boolean operators: `and`, `or`, and `not`.
- Comparisons: equality, inequality, less-than, less-than-or-equal, greater-than, and greater-than-or-equal.
- Conditional expressions using Python's expression form.
- Unary plus and minus.
- List and tuple literals for helper arguments such as `choice(...)`.
- Keyword arguments only where a helper accepts them.

The parser enforces `RULESGEN_DSL_MAX_LENGTH`, currently defaulting to 2000 characters. The validator enforces `RULESGEN_DSL_MAX_DEPTH` and `RULESGEN_DSL_MAX_NODES`, currently defaulting to 12 and 128. These limits are configured in [config.py](../src/rulesgen/core/config.py).

## Runtime Helper Whitelist

The validator permits only the helper names listed in [ALLOWED_CALLS](../src/rulesgen/compiler/validator.py). Runtime behavior is implemented in [build_runtime_locals](../src/rulesgen/compiler/runtime_spec.py).

Implemented row-phase helpers:

- `col(name)`: read a value from the current row.
- `coalesce(*args)`: return the first non-null value.
- `lower(value)` and `upper(value)`: convert a value to a string and change case.
- `concat(*args)`: concatenate values as strings.
- `clamp(value, minimum, maximum)`: bound a numeric value.
- `optional(probability, value)`: return null with a seeded random probability, otherwise return the value.
- `randint(start, end)`: seeded random integer.
- `choice(sequence, weights=None)`: seeded random selection, with optional weights.
- `faker(provider)`: call a provider on a seeded Faker instance.
- `pattern(fmt)`: generate simple pattern strings using `A`, `a`, and `#`.
- `regex(value)`: generate only simple anchored prefix-plus-digits patterns.
- `fk(reference)`: select from a provided reference value pool.

Implemented group-phase helpers:

- `group_sum(key=..., value=...)`: aggregate values by key during dataset generation.
- `group_count(key=...)`: count rows by key during dataset generation.

Group helpers are not supported by the local preview executor. They are compiled and executed during dataset generation, where the engine can build aggregate lookup tables. This is enforced in [local.py](../src/rulesgen/execution/local.py) and [engine.py](../src/rulesgen/execution/engine.py).

## Validation Rules

The validator rejects:

- Any AST node outside [ALLOWED_NODES](../src/rulesgen/compiler/validator.py).
- Bare identifiers that are not whitelisted call targets.
- Calls whose target is not a simple `ast.Name`.
- Unknown helper names.
- `col(...)`, `faker(...)`, `fk(...)`, `pattern(...)`, and `regex(...)` calls without the required string literal argument shape.
- Keyword unpacking.
- More than one aggregate helper in one DSL expression.
- `group_sum(...)` unless it uses exactly `key=...` and `value=...`.
- `group_count(...)` unless it uses exactly `key=...`.

For natural-language translations, dependency references are additionally checked against the supplied schema and the generated target columns in [RuleCompilerService._dependency_errors](../src/rulesgen/compiler/service.py).

## Compilation Contract

Compilation is implemented by [RuleCompilerService.compile](../src/rulesgen/compiler/service.py). It:

1. Parses the expression.
2. Validates it with `DSLValidator`.
3. Compiles the validated AST with Python's `compile(..., mode="eval")`.
4. Produces a `CompiledRule` with:
   - `artifact_id`
   - `target_column`
   - original and normalized expressions
   - dependency list
   - helper function list
   - helper phase metadata
   - aggregate helper metadata, when present
   - source type and explainability trace metadata

The shape of `CompiledRule`, `SemanticFrame`, `AggregateHelperSpec`, and related domain objects is defined in [domain/models.py](../src/rulesgen/domain/models.py).

## Execution Contract

Single-row preview runs through [LocalExecutionAdapter](../src/rulesgen/execution/local.py), which calls [execute_preview_rule](../src/rulesgen/execution/engine.py). The preview runtime uses an empty `__builtins__` mapping and the helper locals produced by [runtime_spec.py](../src/rulesgen/compiler/runtime_spec.py).

Dataset generation runs through [execute_generation_plan](../src/rulesgen/execution/engine.py). It:

- Materializes schema columns as null when missing from input rows.
- Splits rules into row phase and group phase.
- Orders rules by dependency.
- Applies row rules per row.
- Builds aggregate lookups for group helpers.
- Applies group rules per row.
- Classifies columns as `model_generated`, `rule_generated`, or `hybrid`.

The default dataset executor is the subprocess-backed adapter in [opensandbox.py](../src/rulesgen/execution/opensandbox.py). The optional managed OpenSandbox adapter is implemented in [alibaba_opensandbox.py](../src/rulesgen/execution/alibaba_opensandbox.py). Both use the shared runner contract in [opensandbox_runner.py](../src/rulesgen/execution/opensandbox_runner.py).

## Natural-Language Translation Boundary

Natural-language input is not executed directly. It must produce a DSL candidate, and that candidate must pass the same parser and validator as user-supplied DSL.

The compiler path is implemented in [RuleCompilerService.parse](../src/rulesgen/compiler/service.py) and [RuleCompilerService.parse_batch](../src/rulesgen/compiler/service.py). The default stub gateway in [llm_gateway.py](../src/rulesgen/infra/llm_gateway.py) supports a small set of template translations:

- Conditional percentage rules.
- Realistic name generation.
- Foreign-key reference rules.
- Grouped sum rules.
- Simple pattern rules.
- Simple arithmetic addition.

Other gateway backends may return broader DSL candidates, but they are still constrained by the same whitelist and validation rules.

## Source And Test References

Use these files instead of copying code samples into this requirements document:

- DSL dependency and function extraction: [test_compiler.py](../tests/unit/test_compiler.py)
- Attribute-access rejection: [test_compiler.py](../tests/unit/test_compiler.py)
- Local preview execution: [test_compiler.py](../tests/unit/test_compiler.py)
- Group helper metadata extraction: [test_compiler.py](../tests/unit/test_compiler.py)
- Natural-language translation and prompt audit metadata: [test_compiler.py](../tests/unit/test_compiler.py)
- Package-level library helpers: [test_library_api.py](../tests/unit/test_library_api.py)
- HTTP parse, compile, preview, dataset generation, uploads, downloads, and guardrail behavior: [test_api_flow.py](../tests/integration/test_api_flow.py)
