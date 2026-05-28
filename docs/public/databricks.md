# Databricks Models

`rulesgen` can use Databricks-hosted models for natural-language translation.
When configured for Databricks, the LLM gateway uses the official
`databricks_openai.DatabricksOpenAI` client to call Databricks Foundation
Model APIs or customer-deployed Model Serving endpoints.

No `OPENAI_API_KEY` is required for this path. Authentication is resolved by
the Databricks SDK auth chain.

## Install the Extra

Install the Databricks extra when running outside the preconfigured project
environment:

<!-- installs optional Databricks gateway dependencies -->
<!-- skip: start -->
```bash
pip install 'rulesgen[databricks]'
```
<!-- skip: end -->

For a `uv`-managed checkout:

<!-- synchronizes optional Databricks dependencies -->
<!-- skip: start -->
```bash
uv sync --extra databricks
```
<!-- skip: end -->

## Run Inside Databricks

Inside a Databricks notebook or job, the SDK can use runtime credentials
automatically.

<!-- requires a Databricks runtime and approved model endpoint -->
<!-- skip: next -->
```python
import os

from rulesgen import Settings, SourceType, parse_rule

os.environ["RULESGEN_LLM_GATEWAY_BACKEND"] = "litellm"
os.environ["RULESGEN_LLM_MODEL_NAME"] = "databricks-claude-sonnet-4-5"

frame = parse_rule(
    "If job_level is 5 or higher, set bonus to 10 percent of salary.",
    source_type=SourceType.NATURAL_LANGUAGE,
    table_name="employees",
    schema_columns=["salary", "job_level", "bonus"],
    target_column="bonus",
    settings=Settings(),
)

print(frame.dsl_candidate)
```

## Run Outside Databricks

Outside a Databricks runtime, authenticate through the Databricks CLI or
standard Databricks SDK environment variables. Then configure the gateway:

<!-- requires Databricks CLI and an approved workspace -->
<!-- skip: start -->
```bash
databricks auth login --host https://your-workspace.cloud.databricks.com

export RULESGEN_LLM_GATEWAY_BACKEND=litellm
export RULESGEN_LLM_PROVIDER=databricks
export RULESGEN_LLM_MODEL_NAME=databricks-claude-sonnet-4-5
```
<!-- skip: end -->

When `RULESGEN_LLM_PROVIDER=auto`, Databricks is selected if Databricks runtime
or workspace environment variables are present and the Databricks gateway
dependency is installed. If no provider resolves, `rulesgen` falls back to the
stub backend.

## Configure Model Parameters

Some reasoning-tier models reject `temperature` or require provider-specific
completion parameters. Use these settings to omit or override model knobs:

<!-- environment setup for model-specific completion parameters -->
<!-- skip: start -->
```bash
export RULESGEN_LLM_TEMPERATURE=null
export RULESGEN_LLM_EXTRA_COMPLETION_PARAMS='{"max_tokens": 4096, "reasoning_effort": "high"}'
```
<!-- skip: end -->

`RULESGEN_LLM_EXTRA_COMPLETION_PARAMS` is JSON-decoded and merged into the
completion request after default parameters, so it can override defaults for
models that need specialized options.

## Smoke Testing

The repository includes an opt-in Databricks smoke suite. Run it only when you
intend to call a real workspace and incur model-serving costs:

<!-- calls a real Databricks workspace when configured -->
<!-- skip: start -->
```bash
uv run pytest -m databricks tests/integration/test_databricks_openai_smoke.py
```
<!-- skip: end -->

## Related Pages

- [Configuration](configuration.md)
- [Safety Guardrails](safety-guardrails.md)
- [Example Workflows](workflows.md)
