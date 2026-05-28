# NL-to-Python Generation Overview

This document summarizes the implemented Rulesgen workflow for natural-language and DSL-driven tabular rule execution. It intentionally removes exploratory proposals, long implementation sketches, and embedded code samples. Source links point to the current repository implementation and tests.

The current system accepts either a restricted DSL expression or a natural-language rule that must be translated to DSL. In both cases, execution is gated by the same parser, AST validator, helper whitelist, and compiled-rule artifact model.

## Implemented Product Surface

Rulesgen currently exposes:

- A Python library API in [library.py](../src/rulesgen/library.py) and package exports in [__init__.py](../src/rulesgen/__init__.py).
- A FastAPI application assembled in [main.py](../src/rulesgen/main.py).
- Rules endpoints in [api/v1/endpoints/rules.py](../src/rulesgen/api/v1/endpoints/rules.py).
- Dataset upload and generation endpoints in [api/v1/endpoints/datasets.py](../src/rulesgen/api/v1/endpoints/datasets.py).
- Job creation, lookup, dataset download, and artifact download endpoints in [api/v1/endpoints/jobs.py](../src/rulesgen/api/v1/endpoints/jobs.py).
- Health endpoints in [api/v1/endpoints/health.py](../src/rulesgen/api/v1/endpoints/health.py).
- Developer OpenAPI and Swagger UI endpoints in [api/v1/endpoints/docs.py](../src/rulesgen/api/v1/endpoints/docs.py).

The integration flow is covered by [test_api_flow.py](../tests/integration/test_api_flow.py). Package-level library behavior is covered by [test_library_api.py](../tests/unit/test_library_api.py).

## Current Architecture

The implemented layers are:

- HTTP edge: request and response schemas, endpoint functions, auth dependency resolution, and Problem Details error mapping.
- Service layer: orchestration in [rules_service.py](../src/rulesgen/services/rules_service.py), [generation_service.py](../src/rulesgen/services/generation_service.py), and [jobs_service.py](../src/rulesgen/services/jobs_service.py).
- Compiler layer: parsing, validation, natural-language translation orchestration, feedback retry, and compiled-rule creation in [src/rulesgen/compiler](../src/rulesgen/compiler).
- Execution layer: local single-row preview plus dataset generation through subprocess or managed OpenSandbox adapters in [src/rulesgen/execution](../src/rulesgen/execution).
- Repository layer: filesystem-backed stores for rules, jobs, uploads, prompt audits, artifacts, and OSSFS-style local file outputs.
- LLM gateway layer: stub, HTTP, LiteLLM, and Databricks-aware gateway clients in [llm_gateway.py](../src/rulesgen/infra/llm_gateway.py), built through [container.py](../src/rulesgen/container.py).

The application container in [container.py](../src/rulesgen/container.py) wires the compiler, repositories, guardrails, gateway client, local preview adapter, and dataset executor from [Settings](../src/rulesgen/core/config.py).

## Rule Input Flow

DSL input flows directly through:

1. [parse_expression](../src/rulesgen/compiler/parser.py)
2. [DSLValidator](../src/rulesgen/compiler/validator.py)
3. [RuleCompilerService.compile](../src/rulesgen/compiler/service.py)
4. [CompiledRule](../src/rulesgen/domain/models.py)
5. Preview or dataset execution in [engine.py](../src/rulesgen/execution/engine.py)

Natural-language input flows through:

1. Guardrail screening in [guardrails.py](../src/rulesgen/infra/guardrails.py) via the configured gateway client.
2. Gateway translation in [llm_gateway.py](../src/rulesgen/infra/llm_gateway.py).
3. DSL candidate validation through the same parser and validator used for DSL input.
4. Configured feedback retry when the translated candidate fails validation.
5. Semantic frame and explainability trace creation in [service.py](../src/rulesgen/compiler/service.py).
6. Compilation to a `CompiledRule` before execution.

Natural-language input must include an explicit target column unless it is embedded on a schema row. That request shape is enforced in [schemas/rules.py](../src/rulesgen/schemas/rules.py).

## Implemented HTTP Flows

Rules:

- `POST /rules/parse` parses DSL or natural-language input and returns a semantic frame, diagnostics, optional DSL candidate, prompt audit metadata, and LLM metrics when applicable.
- `POST /rules/compile` validates and compiles a DSL expression into a persisted compiled-rule artifact.
- `POST /rules/preview` runs a compiled artifact or expression against one row with the local preview executor.
- `POST /rules/execute` is currently the same local-preview execution path as `/rules/preview`.

Datasets:

- `POST /datasets/uploads` stores a CSV or JSON input dataset for later generation.
- `POST /datasets/generate` creates and executes a generation job from exactly one input source: inline `base_rows` or an uploaded `file_id`.

Jobs:

- `POST /jobs` creates an `execute_preview`, `compile_preview`, `sandbox_execute`, or `generate_dataset` job.
- `GET /jobs/{job_id}` returns the persisted job record.
- `GET /jobs/{job_id}/dataset` downloads the dataset artifact for generation jobs.
- `GET /jobs/{job_id}/artifacts/{artifact_id}` downloads a specific generated artifact.

The request and response contracts live in [schemas/rules.py](../src/rulesgen/schemas/rules.py), [schemas/datasets.py](../src/rulesgen/schemas/datasets.py), and [schemas/jobs.py](../src/rulesgen/schemas/jobs.py).

## Dataset Generation Behavior

Dataset generation is implemented for single-table row sets supplied as inline `base_rows` or uploaded CSV/JSON files. Request validation requires exactly one of those input sources. Inline rows must include a `row_count` equal to the number of rows; uploaded files derive row count from the staged file.

Rules can be supplied either:

- In the top-level `rules` list.
- Embedded in schema rows with `source_text` and `source_type`.
- As existing compiled artifacts via `artifact_id`.

The generation service compiles or resolves the planned rules, classifies each planned target as rule-generated or hybrid, and delegates execution to the configured dataset executor. The execution engine materializes missing schema columns as null, orders row rules by dependencies, executes group helpers after row rules, and writes generated outputs through the artifact path.

Implemented source links:

- Planning: [generation_service.py](../src/rulesgen/services/generation_service.py)
- Job orchestration: [jobs_service.py](../src/rulesgen/services/jobs_service.py)
- Execution plan: [engine.py](../src/rulesgen/execution/engine.py)
- Dataset schemas: [schemas/datasets.py](../src/rulesgen/schemas/datasets.py)
- Dataset integration coverage: [test_api_flow.py](../tests/integration/test_api_flow.py)

## Execution Backends

There are two implemented dataset executor paths:

- Default subprocess dataset executor: [opensandbox.py](../src/rulesgen/execution/opensandbox.py). It writes a manifest and compiled-rule payload under the local OSSFS root, runs [opensandbox_runner.py](../src/rulesgen/execution/opensandbox_runner.py) in a child Python process, and persists dataset, manifest, compiled-rule, log, and diagnostics artifacts.
- Optional managed OpenSandbox adapter: [alibaba_opensandbox.py](../src/rulesgen/execution/alibaba_opensandbox.py). It uploads the same manifest contract into an OpenSandbox-managed environment and downloads the generated dataset and result metadata into local artifact storage.

Single-row previews use [local.py](../src/rulesgen/execution/local.py). The local preview executor intentionally rejects `group_sum` and `group_count` because those helpers require multi-row context.

The backend choice is configured by `RULESGEN_SANDBOX_BACKEND` in [Settings](../src/rulesgen/core/config.py).

## LLM Gateway And Guardrails

The current gateway builder supports:

- Stub gateway for local deterministic translation.
- HTTP gateway that posts translation requests to a configured `/translate` endpoint.
- LiteLLM gateway for provider-backed chat completions.
- Databricks OpenAI-compatible gateway when Databricks is selected and the optional client is available.

Gateway selection is implemented in [build_gateway_client](../src/rulesgen/container.py). Natural-language translation records prompt audit metadata and LLM request metrics, then validates returned DSL candidates before returning semantic frames.

Guardrails run before natural-language text reaches the gateway. The default scanner is heuristic; optional LLM Guard and HTTP scanners are wired in [container.py](../src/rulesgen/container.py) and implemented in [guardrails.py](../src/rulesgen/infra/guardrails.py). Prompt injection blocking is covered by [test_compiler.py](../tests/unit/test_compiler.py) and [test_api_flow.py](../tests/integration/test_api_flow.py).

## Current Safety Boundaries

Implemented safety controls include:

- Restricted AST parsing and validation.
- Explicit helper whitelist.
- Empty `__builtins__` during expression evaluation.
- DSL length, depth, and node-count limits.
- Guardrail screening for natural-language input.
- Feedback retry for invalid LLM-produced DSL candidates.
- Separation between local preview and dataset generation.
- Persisted prompt audits, diagnostics, manifests, logs, and generated artifacts.

The default subprocess dataset executor is not a full sandbox boundary. Stronger process isolation is available only when the managed OpenSandbox adapter is configured and reachable. The AST validator remains the primary non-negotiable safety boundary in all modes.

## Implemented Tests

Use tests as the executable examples for this requirements area:

- Compiler and local preview behavior: [test_compiler.py](../tests/unit/test_compiler.py)
- Public library helpers: [test_library_api.py](../tests/unit/test_library_api.py)
- FastAPI rule, job, dataset, upload, download, metrics, and guardrail flows: [test_api_flow.py](../tests/integration/test_api_flow.py)
- Problem Details contract: [test_problem_details.py](../tests/contract/test_problem_details.py)

This document should be updated only when the implementation changes. Unimplemented parser choices, DSL helpers, isolation models, quality metrics, and multi-table planning ideas belong in a separate design proposal until they become code.
