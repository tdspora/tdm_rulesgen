# Overview

`rulesgen` is a secure rule-processing service for synthetic data workflows.
It accepts rule input as either `natural_language` or a restricted DSL,
translates `natural_language` requests into an untrusted `semantic_frame` plus
DSL candidate, validates the DSL into a `compiled_rule`, supports local
`execution_preview`, and can execute full dataset generation as a tracked
`job`.

The service is designed around a clear trust boundary: LLM output is never
trusted directly. Natural-language output and DSL candidates remain untrusted
until parser and validator checks succeed, and `diagnostics` are part of the
contract at every stage.

## Who this documentation is for

- Teams authoring rules for synthetic data workflows.
- Operators evaluating local preview and full dataset-generation paths.
- Application teams embedding the Python library or HTTP API.
- Platform teams configuring LLM, guardrail, storage, and execution backends.

## What rulesgen does

The core workflow is staged so each step can be inspected independently:

1. Parse rule input into a `semantic_frame`, DSL candidate, and `diagnostics`.
2. Treat `natural_language` output and every DSL candidate as untrusted until
   validation succeeds.
3. Compile validated DSL into a `compiled_rule` artifact.
4. Run an `execution_preview` against a sample row and seed.
5. Generate a target dataset as a tracked `job`.
6. Inspect `diagnostics`, generated artifacts, and job metadata.

`rulesgen` can be used through the HTTP API or directly as a Python library.
The HTTP service provides endpoints for parsing, compilation, preview,
dataset uploads, dataset generation, job polling, and artifact download. The
library API exposes the same core capabilities for in-process use.

## Safety model

`rulesgen` is not a direct natural-language-to-Python executor. A
`natural_language` rule is translated into an LLM-produced `semantic_frame`
and DSL candidate, and both remain untrusted until validation succeeds. The
compiler accepts only a restricted Python-expression subset and a runtime
helper whitelist. The preview executor is intended for fast local feedback;
full dataset generation runs through either the subprocess dataset executor or
the optional Alibaba OpenSandbox adapter.

Pre-LLM guardrails scan natural-language input for prompt injection and
jailbreak attempts. Blocked requests return a standard Problem Details
response without exposing scanner internals to the caller.

## Start here

- [Quick Start](getting-started.md)
- [Example Workflows](workflows.md)
- [API Reference](api-reference.md)
- [Python Library](python-library.md)
- [Configuration](configuration.md)
- [Run Modes](run-modes.md)
- [Safety Guardrails](safety-guardrails.md)
- [Databricks Models](databricks.md)
- [Repository Docs](repository-docs.md)
