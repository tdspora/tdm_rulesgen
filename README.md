# rulesgen

`rulesgen` is a Python library for safe rule parsing, compilation, local preview
execution, and sandbox-backed dataset generation, with an optional
FastAPI/Starlette/Uvicorn application layered on top.

## What is included

- A production-minded ASGI application skeleton under `src/rulesgen/`
- Structured logging, request context propagation, and RFC 9457 problem details
- Versioned API modules with health, rules, dataset, and jobs endpoints
- A restricted DSL compiler built on Python AST validation
- Filesystem-backed repositories for rules, jobs, prompt audits, and artifacts
- A local preview executor, a default subprocess dataset executor, and an optional Alibaba OpenSandbox adapter for full dataset generation
- Tests, CI, and a container build baseline

## Install

Use the package as a library:

```bash
pip install rulesgen
```

Install the optional API layer:

```bash
pip install "rulesgen[api]"
```

For local development in this repository:

```bash
uv sync --extra api --extra dev
```

## Release automation

Pushes to `main` run the CI checks, build the wheel and sdist, and attach those
artifacts to the GitHub Release created by semantic-release.

Before the first automated release, create a baseline tag that matches
`project.version` in `pyproject.toml`, for example:

```bash
git tag v0.1.0
git push origin v0.1.0
```

If branch protection requires pull requests on `main`, allow the GitHub Actions
app to bypass that requirement so semantic-release can push its version bump
commit and the release job can attach wheel/sdist assets to the generated
GitHub Release. [`scripts/configure-github-repo-oss.sh`](scripts/configure-github-repo-oss.sh)
applies the recommended repository and branch-protection settings and prints
the one manual UI step needed to enable the GitHub Actions bypass.

## Library quick start

```python
from rulesgen import compile_rule, preview_rule

compiled_rule = compile_rule(
    'coalesce(col("bonus"), 0) + col("salary")',
    target_column="total_comp",
)
preview = preview_rule(
    compiled_rule,
    row={"salary": 120000, "bonus": 5000},
    seed=99,
)

print(preview.value)
```

## Using `rulesgen` as a library (no service required)

You can embed `rulesgen` directly in your own Python program without starting the
FastAPI application. The high-level entry points are exported from the package:

- `compile_rule`: validate + compile a restricted DSL expression into a `CompiledRule`
- `preview_rule`: run a compiled rule against one row locally (row-phase helpers only)
- `parse_rule`: turn natural language into a `SemanticFrame` (requires an LLM gateway backend)
- `execute_generation_plan`: run a set of compiled rules across many rows in-process

### Compile and preview (pure local execution)

This path does not require the API layer or any external services:

```python
from rulesgen import compile_rule, preview_rule

compiled = compile_rule('0.1 * col("salary") if col("job_level") >= 5 else 0', target_column="bonus")
preview = preview_rule(compiled, row={"salary": 120000, "job_level": 6}, seed=99)
print(preview.value)
```

### Parse natural language (LLM-backed)

If you want to call `parse_rule`, configure the gateway backend via `Settings`
or environment variables (see `.env.example` for all supported `RULESGEN_*`
settings):

```python
from rulesgen import Settings, SourceType, parse_rule

settings = Settings(
    llm_gateway_backend="stub",  # or: "http" / "litellm"
    llm_model_name="rulesgen-local-stub",
)

frame = parse_rule(
    "If job_level is 5 or higher, set bonus to 10 percent of salary.",
    source_type=SourceType.NATURAL_LANGUAGE,
    table_name="employees",
    schema_columns=["salary", "job_level", "bonus"],
    target_column="bonus",
    settings=settings,
)

print(frame.dsl_candidate)
```

### Apply multiple rules to a dataset in-process

If you already have base rows and want to apply several compiled rules locally,
use `execute_generation_plan`:

```python
from rulesgen import Settings, compile_rule, execute_generation_plan

settings = Settings()
rows = [
    {"order_id": "A", "line_amount": 10},
    {"order_id": "A", "line_amount": 5},
    {"order_id": "B", "line_amount": 7},
]

compiled_rules = [
    compile_rule('col("line_amount") * 2', target_column="line_amount_x2", settings=settings),
    compile_rule('group_sum(key=col("order_id"), value=col("line_amount"))', target_column="order_total", settings=settings),
]

run = execute_generation_plan(
    rows=rows,
    compiled_rules=compiled_rules,
    seed=17,
    references={},
    max_length=settings.dsl_max_length,
    max_depth=settings.dsl_max_depth,
    max_nodes=settings.dsl_max_nodes,
)

print(run.rows)
print(run.column_sources)
```

## Quick start

### Run the OpenSandbox-backed flow

The quickest way to validate the OpenSandbox integration end to end is:

```bash
./scripts/quick_start.sh
```

By default the script:

- builds the `rulesgen:local` image for sandbox jobs
- starts or reuses `opensandbox-server`
- starts a local `rulesgen` API with `RULESGEN_SANDBOX_BACKEND=opensandbox`
- uses direct sandbox endpoints (`RULESGEN_OPENSANDBOX_USE_SERVER_PROXY=false`)
- runs the parse, compile, preview, dataset-generation, and job-poll flow below

Requirements: `uv`, Docker, and the Docker Compose plugin.

To use the local subprocess dataset executor instead:

```bash
QUICK_START_BACKEND=subprocess ./scripts/quick_start.sh
```

### Start the service manually

Local subprocess dataset executor:

```bash
uv sync --extra api --extra dev
uv run uvicorn rulesgen.main:app --reload
```

OpenSandbox-backed dataset generation:

```bash
uv sync --extra api --extra dev
docker build -t rulesgen:local .
docker compose -f compose.yaml -f compose.opensandbox.yaml up --build -d opensandbox-server
RULESGEN_SANDBOX_BACKEND=opensandbox \
RULESGEN_OPENSANDBOX_DOMAIN=127.0.0.1:8090 \
RULESGEN_OPENSANDBOX_PROTOCOL=http \
RULESGEN_OPENSANDBOX_USE_SERVER_PROXY=false \
RULESGEN_OPENSANDBOX_IMAGE=rulesgen:local \
uv run uvicorn rulesgen.main:app --reload
```

### Configure the LLM gateway

`rulesgen` supports three LLM gateway modes for natural-language rule
translation: `stub`, `http`, and `litellm`.

#### How the main settings work

- `RULESGEN_LLM_GATEWAY_BACKEND`
  - `stub` (default): do not call an external LLM. This is useful for local
    smoke tests. `RULESGEN_LLM_GATEWAY_URL` is ignored. `RULESGEN_LLM_MODEL_NAME`
    is only recorded in audit metadata.
  - `http`: call a remote gateway service. Set `RULESGEN_LLM_GATEWAY_URL` to
    the gateway root URL; `rulesgen` sends requests to
    `<RULESGEN_LLM_GATEWAY_URL>/translate`. If the URL is empty, the service
    falls back to the `stub` client.
  - `litellm`: call LiteLLM in process. `RULESGEN_LLM_MODEL_NAME` is passed to
    LiteLLM as `model`, and `RULESGEN_LLM_GATEWAY_URL` is passed through as
    LiteLLM `api_base`.

- `RULESGEN_LLM_GATEWAY_URL`
  - Used by the `http` and `litellm` backends.
  - For `http`, set the remote gateway base URL, for example
    `http://127.0.0.1:9000`.
  - For `litellm`, leave it unset to use the built-in OpenAI default
    (`https://api.openai.com/v1`), or set it to the provider-specific or proxy
    base URL required by your LiteLLM model.
  - When it is unset and `RULESGEN_LLM_GATEWAY_BACKEND=litellm`, `rulesgen`
    resolves a default to `https://api.openai.com/v1`. If needed, you can use
    `{RULESGEN_LLM_MODEL_NAME}` placeholder inside `RULESGEN_LLM_GATEWAY_URL`
    to parametrize base URL with a deployment name. For example, `https://ai-proxy.lab.epam.com/openai/deployments/{RULESGEN_LLM_MODEL_NAME}/chat/`

- `RULESGEN_LLM_MODEL_NAME`
  - Used directly by the `litellm` backend as the model identifier.
  - Not used by the local `http` client. In `stub` mode it is only recorded in
    audit metadata.

#### Examples

Default OpenAI through `litellm`:

```bash
RULESGEN_LLM_GATEWAY_BACKEND=litellm
RULESGEN_LLM_MODEL_NAME=gpt-4o-mini
RULESGEN_LLM_PROMPT_TEMPLATE_VERSION=v1
OPENAI_API_KEY=your-openai-key
```

You can omit `RULESGEN_LLM_GATEWAY_URL` here; `rulesgen` defaults it to
`https://api.openai.com/v1`.

OpenAI-compatible proxy through `litellm`:

```bash
RULESGEN_LLM_GATEWAY_BACKEND=litellm
RULESGEN_LLM_MODEL_NAME=openai/mistral
RULESGEN_LLM_GATEWAY_URL=http://127.0.0.1:4000
RULESGEN_LLM_PROMPT_TEMPLATE_VERSION=v1
OPENAI_API_KEY=proxy-or-provider-key
```

For OpenAI-compatible endpoints, LiteLLM expects a model name with an
`openai/` prefix. Set `RULESGEN_LLM_GATEWAY_URL` to the `api_base` expected by
that endpoint, and do not include endpoint-specific suffixes such as
`/chat/completions`.

Azure deployment through `litellm`:

```bash
RULESGEN_LLM_GATEWAY_BACKEND=litellm
RULESGEN_LLM_MODEL_NAME=gpt-4o-mini
RULESGEN_LLM_GATEWAY_URL=https://my-resource.openai.azure.com/
RULESGEN_LLM_PROMPT_TEMPLATE_VERSION=v1
AZURE_API_KEY=your-azure-key
AZURE_API_VERSION=2024-06-01
```

Remote HTTP gateway:

```bash
RULESGEN_LLM_GATEWAY_BACKEND=http
RULESGEN_LLM_GATEWAY_URL=http://127.0.0.1:9000
RULESGEN_LLM_PROMPT_TEMPLATE_VERSION=v1
```

With this configuration, `rulesgen` calls
`http://127.0.0.1:9000/translate`. `RULESGEN_LLM_MODEL_NAME` is not sent by the
local client for the `http` backend.

Stub backend for local smoke tests:

```bash
RULESGEN_LLM_GATEWAY_BACKEND=stub
RULESGEN_LLM_MODEL_NAME=rulesgen-local-stub
RULESGEN_LLM_PROMPT_TEMPLATE_VERSION=v1
```

For `litellm`, also provide the provider credentials required by the selected
model, for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or
Azure variables such as `AZURE_API_KEY` and `AZURE_API_VERSION`.

The packaged prompt resources live under
`src/rulesgen/resources/prompts/nl_to_dsl/v1/`. Semantic-cache files default to
`.rulesgen-data/semantic-cache/` and can be tuned with the `RULESGEN_LLM_*`
settings from `.env.example`.

In another terminal:

```bash
export BASE_URL=http://127.0.0.1:8000
curl -s "$BASE_URL/health/ready"
```

### Start with Docker Compose

Default local stack with the current subprocess dataset executor:

```bash
docker compose up --build
```

OpenSandbox control plane for the host-run API or `./scripts/quick_start.sh`:

```bash
docker compose -f compose.yaml -f compose.opensandbox.yaml up --build opensandbox-server
```

The OpenSandbox quick-start path expects the built `rulesgen:local` image to be available for sandbox jobs and uses direct sandbox endpoint access from the host-run API.

### End-to-end flow

#### 1. Parse a natural-language rule into a `semantic_frame`

This returns the inferred intent, a DSL candidate, diagnostics, and prompt-audit
metadata from the gateway layer.

```bash
curl -s "$BASE_URL/rules/parse" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "employees",
    "schema": [
      {"name": "salary", "type": "FLOAT", "nullable": false, "source": "syngen"},
      {"name": "job_level", "type": "INT", "nullable": false, "source": "syngen"},
      {
        "name": "bonus",
        "type": "FLOAT",
        "nullable": true,
        "source": "rule",
        "source_text": "If job_level is 5 or higher, set bonus to 10 percent of salary.",
        "source_type": "natural_language"
      }
    ]
  }'
```

Look for:

- `dsl_candidate`
- `diagnostics`
- `prompt_audit`
- `prompt_audits`
- `metrics`
- `explainability_trace`

For schema-embedded rule requests, the target column comes from the schema row
`name`. The row-level `source_type` should be `natural_language` or
`domain_specific_language`.

#### 2. Compile a restricted DSL expression into a `compiled_rule`

Copy the `dsl_candidate` from the parse response, or compile a DSL expression
directly:

```bash
curl -s "$BASE_URL/rules/compile" \
  -H "Content-Type: application/json" \
  --data-binary @- <<'EOF'
{
  "expression": "0.1 * col('salary') if col('job_level') >= 5 else 0",
  "target_column": "bonus"
}
EOF
```

Copy the returned `artifact_id` for the preview and job calls below.

#### 3. Preview the compiled rule with one sample row

`/rules/preview` uses the local preview executor and is limited to row-phase
helpers.

```bash
curl -s "$BASE_URL/rules/preview" \
  -H "Content-Type: application/json" \
  -d '{
    "artifact_id": "<artifact_id>",
    "row": {
      "salary": 120000,
      "job_level": 6
    },
    "seed": 99
  }'
```

Look for `value`, `execution_mode`, and `diagnostics`.

#### 4. Generate a dataset with an aggregate rule

`/datasets/generate` creates a generation job and returns the stable `job_id`
that SynGen or other clients can poll.

```bash
curl -s "$BASE_URL/datasets/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "row_count": 3,
    "base_rows": [
      {"order_id": "A", "line_amount": 10},
      {"order_id": "A", "line_amount": 5},
      {"order_id": "B", "line_amount": 7}
    ],
    "schema": [
      {"name": "order_id", "type": "STRING", "nullable": false, "source": "syngen"},
      {"name": "line_amount", "type": "INT", "nullable": false, "source": "syngen"},
      {
        "name": "order_total",
        "type": "INT",
        "nullable": true,
        "source": "rule",
        "source_text": "group_sum(key=col(\"order_id\"), value=col(\"line_amount\"))",
        "source_type": "domain_specific_language"
      }
    ],
    "seed": 17
  }'
```

The response includes:

- `job_id`
- `status`
- `planned_column_sources`
- `llm_metrics` when any rule was translated from natural language
- `diagnostics`

#### 5. Poll the job and inspect generated artifacts

```bash
curl -s "$BASE_URL/jobs/<job_id>"
```

The job response includes:

- `result.output_path` for the generated dataset
- `artifacts` entries for the dataset, manifest, diagnostics, and execution log
- `llm_metrics` for the natural-language translation session, when applicable
- `diagnostics` from the sandbox execution path

By default, generated files are written under the configured local OSSFS root
(`.rulesgen-data/ossfs/` unless overridden with environment variables). With
`RULESGEN_SANDBOX_BACKEND=subprocess`, full dataset generation runs through the
local subprocess dataset executor. With
`RULESGEN_SANDBOX_BACKEND=opensandbox`, the same manifest is uploaded into an
Alibaba OpenSandbox-managed container and the generated dataset is downloaded
back into the local OSSFS root.

## Useful commands

```bash
uv sync --extra api --extra dev
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy src
uv run pip-audit
```

## Shared project guidance

- Domain vocabulary for agents and contributors lives in `docs/domain-dictionary.md`.
- Cursor rules for this repo live in `.cursor/rules/`.

## API surface

- `GET /health/live`
- `GET /health/ready`
- `POST /rules/parse`
- `POST /rules/compile`
- `POST /rules/preview`
- `POST /rules/execute`
- `POST /datasets/generate`
- `POST /jobs`
- `GET /jobs/{job_id}`

## Architecture notes

The HTTP layer remains thin. Routers depend on services, services depend on compiler and repository interfaces, and the compiler executes only validated AST artifacts with a restricted runtime surface.

Natural-language parsing flows through an LLM gateway adapter that returns an untrusted `semantic_frame` plus DSL candidate, and the service only compiles the candidate after AST validation succeeds.

Preview execution uses the local preview executor for row-phase helpers, while
full dataset generation uses either the default subprocess dataset executor or
the Alibaba OpenSandbox adapter, both of which preserve the same manifest and
artifact contract under the configured local OSSFS root.

## License

This project is licensed under the **Apache License 2.0**. See [`LICENSE`](LICENSE) for the full text and [`NOTICE`](NOTICE) for copyright attribution.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). This project follows the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Report security issues according to [`SECURITY.md`](SECURITY.md).
