# Rulesgen Glossary

Single source of truth for vocabulary used in this project — business-facing terms a Product Owner or Business Analyst can quote in user stories and acceptance criteria, **and** the technical / runtime terms agents and contributors use inside the codebase.

When a term appears in `[[brackets]]` it is defined elsewhere in this document. There are no cross-references to other dictionaries; this file is authoritative.

---

## 1. Product surface

| Term | Definition |
|---|---|
| **Rulesgen service** | The FastAPI application + Python library (`rulesgen`) that parses, validates, compiles, previews, and executes safe rule expressions over tabular data. |
| **Library API** | Programmatic Python interface (`rulesgen.library`) for embedding rule compilation and execution inside calling applications. Public surface, governed by [[Conventional Commits]] and [[semantic-release]]. |
| **HTTP API** | Versioned REST surface under `/v1/...`, composed in `src/rulesgen/main.py:create_app()`. Errors follow [[Problem Details]]. |
| **CLI / scripts** | The packaged wheel exposes the library only; no console-script entry points. Operators interact through the [[HTTP API]] or by importing the [[Library API]]. |
| **Container distribution** | Docker image built from `Dockerfile`; runtime topology defined in `compose.yaml` (library + API) and `compose.opensandbox.yaml` (adds [[OpenSandbox]] backend). |

## 2. Rule input

| Term | Definition |
|---|---|
| **[[rule]]** | A user-authored expression that computes or constrains a [[target column]]. |
| **[[source_type]]** | How the rule entered the system. Current values: `dsl`, `natural_language`. |
| **[[DSL]] rule** | A rule already expressed in the restricted Python-expression subset that the [[compiler]] accepts. |
| **[[natural language]] rule** | Plain-English description that must be translated to [[DSL]] before execution (see [[NL translation]]). |
| **[[target column]]** (`target_column`) | The output column a [[rule]] is intended to populate. |
| **[[target dataset]]** | The tabular dataset produced by executing a set of [[compiled rules]] against [[schema columns]] and seed data. |
| **[[schema columns]]** (`schema_column`) | Typed table metadata supplied by the caller. Grounds [[NL translation]] and validation. In API requests it can also carry embedded rule input for rule-generated columns via row-level `source_text` and `source_type`. |
| **Sample dataset** | Reference / preview data the user provides (e.g., `samples/orders.csv`) so [[rules]] can be previewed before full generation. |
| **[[dependencies]]** | Columns referenced through `col("...")` inside a rule expression. |
| **[[functions]]** | Runtime helpers referenced by the rule expression (see [[runtime helpers]]). |
| **[[intent]]** | The high-level rule category. Current intents: `dsl_expression`, `arithmetic`, `conditional`, `faker`, `pattern`, `foreign_key`, `aggregate`, `unknown`. |

## 3. NL-to-DSL translation

| Term | Definition |
|---|---|
| **[[NL translation]]** | The process of converting a [[natural language]] rule into a [[DSL]] candidate via the [[LLM gateway]]. |
| **[[LLM gateway]]** | The adapter that translates `natural_language` input into a [[semantic frame]] plus DSL candidate and records [[prompt audit]] metadata. `litellm`-backed; endpoints and keys come from `Settings` only — never hardcoded. See [[customer-approved endpoint]]. |
| **[[LiteLLM backend]]** | The in-process [[LLM gateway]] backend that talks to OpenAI, Anthropic, and Gemini through one client interface. |
| **[[customer-approved endpoint]]** | An LLM URL that the customer has explicitly authorized for egress; supplied via env-var name. Egress to any other URL is a security incident. |
| **[[prompt pack]]** | Versioned markdown prompts (system / request / feedback) used during [[NL translation]]. |
| **[[semantic frame]]** (`semantic_frame`) | Structured understanding of a rule before compilation — intent, dependencies, helper functions, entities, diagnostics. For `natural_language` input, it is the typed output an LLM translator must produce before the rule can continue through validation. |
| **[[feedback retry]]** | Bounded repair loop in which compiler diagnostics are fed back to the LLM so it can correct only the invalid DSL elements. |
| **[[prompt audit]]** (`prompt_audit`) | Persisted record of one [[NL translation]] attempt: prompt, response summary, template version, prompt-security flags. Used for audit + replay. |
| **[[semantic cache]]** (`semantic_cache`) | GPTCache-backed similarity cache for [[NL translation]] requests, scoped by prompt version + model + table + schema fingerprint + requested targets. Cache keys are hashed so they do not expose raw input. |
| **[[LLM request metrics]]** (`llm_request_metrics`) | Aggregated token / latency / cache / cost metadata for one NL translation session. Surfaced for SLO and cost reporting. |

## 4. Compilation

| Term | Definition |
|---|---|
| **[[compiler]]** | Pipeline (`src/rulesgen/compiler/`) that lexes, parses, validates, and normalizes a DSL expression into a [[runtime spec]]. |
| **[[parse]]** | Turn input into a semantic understanding plus [[diagnostics]]. |
| **[[compile]]** | Validate and turn a safe DSL expression into an executable artifact. |
| **[[validator]]** | The safety-critical AST checker (`compiler/validator.py`). Rejects imports, attribute escapes, dunder access, builtins, and any node not in the [[safe subset]]. Any relaxation is a security event. |
| **[[safe subset]]** / **[[whitelist]]** | The allowed set of AST node types and runtime helper calls the [[validator]] accepts. See [[runtime helpers]] for the helper whitelist. |
| **[[validated AST]]** | The trusted intermediate form after parser and validator checks pass. |
| **[[untrusted rule input]]** | Any user-authored NL or DSL content. Treat it as hostile until validated. |
| **[[normalized expression]]** (`normalized_expression`) | The canonical expression string derived from AST validation. |
| **[[runtime spec]]** / **[[compiled rule]]** (`compiled_rule`) | The validated, executable artifact emitted by the [[compiler]]; stores the normalized expression, dependency list, helper list, and compiled code object. Created from validated Python AST, never from string-built Python source. |
| **[[diagnostics]]** | Structured feedback for syntax, safety, and validation failures. |

## 5. Execution

| Term | Definition |
|---|---|
| **[[execute]]** / **[[preview]]** | Run a [[compiled rule]] against sample inputs. |
| **[[execution backend]]** | One of: `local` (in-process preview), `opensandbox` (subprocess-based), `alibaba_opensandbox` (managed sandbox). Configured per environment. |
| **[[execution adapter]]** | The component that runs compiled rules in a concrete runtime. Synonym for a single [[execution backend]] implementation. |
| **[[local preview executor]]** | The current adapter in `src/rulesgen/execution/local.py`. Supports [[row-phase helpers]] but intentionally rejects [[aggregate helpers]] during preview. |
| **[[subprocess dataset executor]]** | The default adapter in `src/rulesgen/execution/opensandbox.py`. Stages manifests and outputs under the local [[OSSFS]] root and runs the shared runner module in a child Python process. Preserves current behavior but is not a full isolation boundary. |
| **[[Alibaba OpenSandbox adapter]]** | The optional adapter in `src/rulesgen/execution/alibaba_opensandbox.py` that uploads the same manifest contract into an OpenSandbox-managed container and downloads the generated dataset back into local [[OSSFS]]-backed storage. |
| **[[OpenSandbox]]** | Isolated code-execution backend. Two flavors: the [[subprocess dataset executor]] (default, local) and the [[Alibaba OpenSandbox adapter]] (opt-in, managed). |
| **[[sandbox isolation]]** / **[[sandbox]]** | The trust boundary preventing generated code from accessing the host process. Defense-in-depth goal; the current local backend has no full process isolation, which is why the [[validator]] is non-negotiable. |
| **[[execution preview]]** (`execution_preview`) | The result of running one [[compiled rule]] against one preview row and seed; used for fast iteration before full generation. |
| **[[helper_phase]]** | Whether a runtime helper is evaluated in the `row` phase or the `group` phase. |
| **[[row-phase helper]]** | A helper that can be evaluated from one row plus runtime context. Examples: `col`, `coalesce`, `faker`, `fk`. |
| **[[group-phase helper]]** | A helper that requires multi-row context. Examples: `group_sum`, `group_count`. |
| **[[aggregate_helper]]** | Extracted metadata for a single `group_sum` or `group_count` helper used by a compiled rule. |
| **[[seed]]** | The deterministic input used to initialize runtime randomness and Faker output. |
| **[[references]]** | External value pools used for helpers such as `fk("table.column")`. |
| **[[column_source]]** | How a dataset column is produced during generation. Current values: `model_generated`, `rule_generated`, `hybrid`. |
| **[[job]]** | A tracked generation or execution request with lifecycle state (`running`, `succeeded`, `failed`). |
| **[[generated artifact]]** (`generated_artifact`) | Metadata pointing to a manifest, dataset output, diagnostics file, or execution log written to local [[OSSFS]]-backed storage. |

## 6. Runtime helpers

These names are part of the current DSL/runtime contract and should be treated as the canonical [[whitelist]] unless intentionally extended. They are the only callables the [[validator]] permits.

| Helper | Phase | Notes |
|---|---|---|
| `col` | row | Reference another column in the same row. |
| `coalesce` | row | First non-null among the arguments. |
| `concat` | row | String concatenation. |
| `lower` | row | Lowercase a string. |
| `upper` | row | Uppercase a string. |
| `clamp` | row | Constrain a numeric value to `[min, max]`. |
| `optional` | row | Wrap an expression that may be absent. |
| `randint` | row | Seeded random integer. |
| `faker` | row | Seeded Faker provider output. |
| `pattern` | row | Generate from a pattern template. |
| `regex` | row | Generate from a regular expression. |
| `fk` | row | Pull a value from a foreign-key [[references]] pool, e.g. `fk("table.column")`. |
| `group_sum` | group | Aggregate sum across a group. Not supported in [[local preview executor]]. |
| `group_count` | group | Aggregate count across a group. Not supported in [[local preview executor]]. |

## 7. Architecture layers

| Term | Definition |
|---|---|
| **[[HTTP edge]]** | FastAPI routers, request schemas, middleware, and exception mapping under `src/rulesgen/api/` and `src/rulesgen/middleware/`. |
| **[[service layer]]** | Orchestration logic in `src/rulesgen/services/`. |
| **[[compiler layer]]** | Parsing, validation, normalization, and compilation in `src/rulesgen/compiler/`. |
| **[[execution adapter]] layer** | Adapters that run compiled rules in a concrete runtime; see [[execution backend]]. |
| **[[repository]]** | Persistence abstraction for [[compiled rules]], [[jobs]], [[prompt audits]], and [[generated artifacts]]. The default app wiring uses local filesystem-backed repositories; in-memory repositories remain available for tests and narrow slices. |
| **[[OSSFS]]** | Local-only file root used by the current implementation for generated manifests, sandbox results, and dataset outputs. Treat any path under it as untrusted output. |

## 8. Quality & contract terms

| Term | Definition |
|---|---|
| **[[Problem Details]]** | RFC 7807 JSON error format. Every API error MUST conform; no bare `HTTPException(detail=str)` allowed. |
| **[[Pydantic v2]]** | Mandated validation library for all schemas and settings. v1 syntax is forbidden. |
| **[[Conventional Commits]]** | Commit message convention (`feat:`, `fix:`, `chore:`, `BREAKING CHANGE:`). Drives `python-semantic-release` version bumps. |
| **[[semantic-release]]** | Automated versioning + changelog tool; owns `pyproject.toml:project.version`. Hand-editing the version is forbidden. |
| **[[backward compatibility]]** | A change is backward-compatible when: (a) existing [[Library API]] callers still compile and run, (b) existing [[HTTP API]] requests still return the same status + body shape, (c) existing accepted [[DSL]] forms still compile to the same [[runtime spec]] semantics. A break requires a `BREAKING CHANGE:` footer. |
| **[[contract test]]** | Test in `tests/contract/` that pins the shape of an HTTP response (status, headers, body schema). |
| **[[integration test]]** | Test in `tests/integration/` that drives the FastAPI app via `TestClient`. |
| **[[regression test]]** | A test that reproduces a previously reported bug before the fix and is expected to pass after. |
| **[[acceptance criteria]] format** | We write Gherkin (`GIVEN…WHEN…THEN…`) for user-facing flows and tabular contracts for API shape changes. |

## 9. Operational / security terms

| Term | Definition |
|---|---|
| **[[secret hygiene]]** | Three rules: (a) no value in source / commit / log, (b) all credential fields are env-var **names**, (c) `.env*`, `~.env`, `.cursor/mcp.json`, `~/.ssh/**`, `~/.aws/**` are denied for read by the harness. |
| **[[customer-controlled storage]]** | `.rulesgen-data/`, `~.rulesgen-data/`, [[OSSFS]] roots — never committed; retention defined by the customer. |
| **[[deployment topology]]** | Where each component runs in a customer environment: API container, [[LLM gateway]], [[OpenSandbox]], [[semantic cache]] backend. Encoded in `compose*.yaml`; changes require [[release-engineer]] sign-off. |

## 10. Agent harness terms

These are the harness primitives a PO will see in conversations with the delivery team.

| Term | Definition |
|---|---|
| **[[harness]]** | The collection of files under `.claude/` plus `CLAUDE.md` that conditions Claude Code's behavior on this repository. |
| **[[CLAUDE.md]]** | The always-loaded project context file at the repo root. Authoritative for project facts, escalation triggers, and engineering standards. |
| **[[CLAUDE.local.md]]** | Gitignored developer-local overrides. Never committed. |
| **[[agent (subagent)]]** | A focused role with its own model, tools, and prompt under `.claude/agents/`. Today: `rulesgen-architect`, `code-reviewer`, `security-reviewer`, `codebase-researcher`, `implementation-engineer`, `test-engineer`, `integration-test-engineer`, `release-engineer`. |
| **[[skill]]** | A trigger-based prompt fragment under `.claude/skills/<name>/SKILL.md`. Loaded only when its trigger matches the user's intent; cheap on context. |
| **[[rule]] (harness)** | A persistent constraint under `.claude/rules/` always loaded as context. Not to be confused with the product [[rule]]. |
| **[[settings.json]]** | The `allow` / `ask` / `deny` permission matrix for tool calls. |
| **[[escalation trigger]]** | A change category that requires explicit human approval before the agent may proceed (see CLAUDE.md "Escalation triggers"). |
| **[[approval text]]** | Literal strings a human types to authorize a paused action: `approved`, `approved: <constraint>`, or `deny`. Anything else (`ok`, thumbs-up, silence) is **not** approval. |
| **[[Definition of Done]]** | A change is done when: implementation + tests are merged behind a [[Conventional Commits]] message, all CI gates pass (ruff, mypy, pytest, pip-audit, build), the [[changelog]] reflects user-visible impact, and no [[escalation trigger]] is open. |
| **[[harness change]]** | An edit to files under `.claude/` or `docs/agent-harness/`. Requires `rulesgen-harness-update` skill + explicit human [[approval text]]. |

## 11. Canonical pipeline

The end-to-end pipeline, in the order it runs. Every term is defined above.

1. User input arrives as [[natural language]] or [[DSL]].
2. If the input is `natural_language`, the [[LLM gateway]] translates one explicit batch of [[target column]] requests into [[semantic frame]] data and DSL candidates. If the input is already `dsl`, the system [[parses|parse]] it directly.
3. [[Prompt pack]] resources and [[semantic cache]] lookups can short-circuit repeated NL requests before a provider call.
4. DSL is validated against the [[whitelist]] by the [[validator]].
5. Invalid DSL candidates can be sent back through a [[feedback retry]] for bounded repair.
6. A [[compiled rule]] is created from the [[validated AST]], not from string-built Python source.
7. The rule runs inside a restricted [[preview]] runtime via the [[local preview executor]].
8. Full dataset generation is planned by the [[service layer]] and executed through an [[execution adapter]] ([[subprocess dataset executor]] or [[Alibaba OpenSandbox adapter]]).
9. The [[HTTP API]] returns [[diagnostics]], [[prompt audits]], [[LLM request metrics]], [[compiled rule]] metadata, an [[execution preview]] value, [[generated artifact]] locations, or a [[job]] record.

## 12. Roadmap vocabulary

These terms matter for future work even where the current code only implements part of them.

| Term | Definition |
|---|---|
| **[[hybrid generation]]** | Combine model-driven generation with rule-driven derivation in one workflow. |
| **[[column planner]]** | Classify columns as model-generated, rule-generated, or hybrid and resolve dependency ordering. |
| **[[explainability trace]]** | Show the path from NL to LLM-produced [[semantic frame]] to DSL to [[validated AST]] to execution artifact. |
| **[[defense in depth]]** | Combine AST validation, runtime restrictions, resource limits, and stronger process or OS isolation. |

## 13. Preferred wording for agents

When agents write code comments, commit messages, PR descriptions, error messages, or any user-visible text, use these forms — they keep the trust boundary legible.

- Say *restricted DSL expression*, not *arbitrary Python snippet*.
- Say *validated AST* or *compiled rule artifact*, not *eval'd user code*.
- Say *LLM-translated DSL candidate* or *LLM-produced semantic frame* when describing the NL translation stage.
- Say *preview executor* for the current local runtime.
- Say *subprocess dataset executor* for the default local dataset-generation path.
- Say *Alibaba OpenSandbox adapter* for the optional remote dataset-generation backend.
- Say *aggregate helpers are planned but not supported in local preview* when discussing `group_sum` and `group_count`.

## 14. How to use this glossary in requirements

Recommended PRD / user-story template:

> **As a** *<role>*, **I want** *<feature>* **so that** *<value>*.
>
> **Acceptance criteria** (Gherkin):
> - **GIVEN** a *[[schema columns]]* set including `<col>` and a *[[sample dataset]]* …
> - **WHEN** I submit a *[[natural language]] rule* through the *[[HTTP API]]* …
> - **THEN** the *[[NL translation]]* produces a *[[DSL]] rule* and an *[[execution preview]]* on row 0 …
> - **AND** the response conforms to *[[Problem Details]]* on the unhappy path.
>
> **Definition of Done** — see [[Definition of Done]].

Always link out via `[[bracket]]` syntax so reviewers can click through to definitions. If you find a term in a draft that is **not** in this glossary, add it here first; do not invent a synonym. Undefined vocabulary is a leading cause of acceptance-test churn.

---

## 15. Maintenance

- This file is the single authoritative glossary for the project — business **and** technical vocabulary live here together.
- When a new term enters PRDs, JIRA, design docs, code, or DSL, add it in the same change. Cross-link with `[[term]]`; do not re-define.
- When a [[runtime helper]] is added or removed, update §6 in the same commit as the code change.
- When a new [[intent]], [[helper_phase]], pipeline stage, or architectural term appears, update §2–§7 and the [[canonical pipeline]] in §11.
- Any change to this file is a [[harness change]] and follows the `rulesgen-harness-update` skill flow with explicit human [[approval text]].
