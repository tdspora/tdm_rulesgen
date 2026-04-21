# Rulesgen Domain Dictionary

## Purpose

This glossary gives agents and contributors a shared vocabulary for the `rulesgen` service. It is based on the architecture and DSL design docs plus the current code under `src/rulesgen`.

## Core product terms

- `rulesgen`: the FastAPI service that parses, validates, compiles, previews, and executes safe rule expressions for synthetic data generation workflows.
- `rule`: a user-authored expression that computes or constrains a target column.
- `target_column`: the output column a rule is intended to populate.
- `source_type`: how the rule entered the system. Current values are `dsl` and `natural_language`.
- `semantic_frame`: the structured understanding of a rule before compilation. For `natural_language` input, it is the typed output that an LLM translator must produce before the rule can continue through validation. It captures intent, dependencies, helper functions, entities, and diagnostics.
- `compiled_rule`: the validated executable artifact produced from a DSL expression. It stores the normalized expression, dependency list, helper list, and compiled code object.
- `execution_preview`: the result of running one compiled rule against one preview row and seed.
- `prompt_audit`: the persisted record of the LLM gateway prompt, response summary, template version, and prompt-security flags for one `natural_language` translation attempt.
- `generated_artifact`: metadata that points to a manifest, dataset output, diagnostics file, or execution log written to local OSSFS-backed storage.
- `job`: a tracked generation or execution request with lifecycle state such as `running`, `succeeded`, or `failed`.

## Pipeline terms

The canonical pipeline is:

1. User input arrives as natural language or DSL.
2. If the input is `natural_language`, an LLM translates it into a `semantic_frame` and DSL candidate; if the input is already `dsl`, the system parses it directly.
3. DSL is validated against an AST whitelist.
4. A `compiled_rule` is created from validated Python AST, not string-built Python source.
5. The rule runs inside a restricted preview runtime.
6. Full dataset generation is planned by the trusted service layer and executed through an isolated execution adapter.
7. The API returns diagnostics, compiled metadata, a preview value, generated artifact locations, or a job record.

Use these names when describing the system:

- `parse`: turn input into a semantic understanding plus diagnostics.
- `compile`: validate and turn a safe DSL expression into an executable artifact.
- `execute` or `preview`: run a compiled rule against sample inputs.
- `diagnostics`: structured feedback for syntax, safety, and validation failures.

## Rule semantics

- `dsl`: the internal contract for executable rules. In the current service it is a restricted Python-expression subset.
- `natural_language`: a higher-level source form that should be translated by an LLM into the DSL contract before execution, with the generated output still treated as untrusted until validation passes.
- `dependencies`: columns referenced through `col("...")`.
- `functions`: runtime helpers referenced by the rule expression.
- `normalized_expression`: the canonical expression string derived from AST validation.
- `intent`: the high-level rule category. Current intents include `dsl_expression`, `arithmetic`, `conditional`, `faker`, `pattern`, `foreign_key`, `aggregate`, and `unknown`.
- `helper_phase`: whether a runtime helper is evaluated in the `row` phase or the `group` phase.
- `aggregate_helper`: extracted metadata for a single `group_sum` or `group_count` helper used by a compiled rule.

## Runtime helper vocabulary

These helper names are part of the current DSL/runtime contract and should be treated as the canonical whitelist unless intentionally extended:

- `col`
- `coalesce`
- `concat`
- `lower`
- `upper`
- `clamp`
- `optional`
- `randint`
- `faker`
- `pattern`
- `regex`
- `fk`
- `group_sum`
- `group_count`

## Execution model

- `row-phase helper`: a helper that can be evaluated from one row plus runtime context. Examples: `col`, `coalesce`, `faker`, `fk`.
- `group-phase helper`: a helper that requires multi-row context, such as `group_sum` and `group_count`.
- `local preview executor`: the current adapter in `src/rulesgen/execution/local.py`. It supports row-phase helpers but intentionally rejects aggregate helpers during preview.
- `subprocess dataset executor`: the default adapter in `src/rulesgen/execution/opensandbox.py`. It stages manifests and outputs under the local OSSFS root and runs the shared runner module in a child Python process. This preserves current behavior but is not a full isolation boundary.
- `Alibaba OpenSandbox adapter`: the optional adapter in `src/rulesgen/execution/alibaba_opensandbox.py` that uploads the same manifest contract into an OpenSandbox-managed container and downloads the generated dataset back into local OSSFS-backed storage.
- `seed`: the deterministic input used to initialize runtime randomness and Faker output.
- `references`: external value pools used for helpers such as `fk("table.column")`.
- `column_source`: how a dataset column is produced during generation. Current values are `model_generated`, `rule_generated`, and `hybrid`.

## Safety terms

- `validated AST`: the trusted intermediate form after parser and validator checks pass.
- `whitelist`: the allowed set of syntax nodes and runtime helper calls.
- `untrusted rule input`: any user-authored NL or DSL content. Treat it as hostile until validated.
- `sandbox`: a defense-in-depth goal. The current implementation has a restricted runtime and no builtins, but it is not a complete isolation boundary yet.

## Architecture terms

- `HTTP edge`: FastAPI routers, request schemas, middleware, and exception mapping.
- `service layer`: orchestration logic in `src/rulesgen/services`.
- `compiler layer`: parsing, validation, normalization, and compilation in `src/rulesgen/compiler`.
- `execution adapter`: the component that runs compiled rules in a concrete runtime.
- `LLM gateway`: the adapter that translates `natural_language` input into a `semantic_frame` plus DSL candidate and records `prompt_audit` metadata.
- `OSSFS`: the local-only file root used by the current implementation for generated manifests, sandbox results, and dataset outputs.
- `repository`: persistence abstraction for compiled rules, jobs, prompt audits, and generated artifacts. The default app wiring uses local filesystem-backed repositories, while in-memory repositories remain available for tests and narrow slices.

## Roadmap terms from the design docs

These terms matter for future work even where the current code only implements part of them:

- `hybrid generation`: combine model-driven generation with rule-driven derivation.
- `column planner`: classify columns as model-generated, rule-generated, or hybrid and resolve dependency ordering.
- `explainability trace`: show the path from NL to LLM-produced semantic frame to DSL to validated execution artifact.
- `defense in depth`: combine AST validation, runtime restrictions, resource limits, and stronger process or OS isolation.

## Preferred wording for agents

- Say `restricted DSL expression`, not `arbitrary Python snippet`.
- Say `validated AST` or `compiled rule artifact`, not `eval'd user code`.
- Say `LLM-translated DSL candidate` or `LLM-produced semantic frame` when describing the NL translation stage.
- Say `preview executor` for the current local runtime.
- Say `subprocess dataset executor` for the default local dataset-generation path.
- Say `Alibaba OpenSandbox adapter` for the optional remote dataset-generation backend.
- Say `aggregate helpers are planned but not supported in local preview` when discussing `group_sum` and `group_count`.
- Update this file when adding a new core runtime helper, intent, pipeline stage, or architectural term.
