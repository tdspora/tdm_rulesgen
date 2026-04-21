# rulesgen

`rulesgen` is a FastAPI/Starlette/Uvicorn service for safe rule parsing,
compilation, local preview execution, and sandbox-backed dataset generation.

## What is included

- A production-minded ASGI application skeleton under `src/rulesgen/`
- Structured logging, request context propagation, and RFC 9457 problem details
- Versioned API modules with health, rules, dataset, and jobs endpoints
- A restricted DSL compiler built on Python AST validation
- Filesystem-backed repositories for rules, jobs, prompt audits, and artifacts
- A local preview executor, a default subprocess dataset executor, and an optional Alibaba OpenSandbox adapter for full dataset generation
- Tests, CI, and a container build baseline

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
uv sync --extra dev
uv run uvicorn rulesgen.main:app --reload
```

OpenSandbox-backed dataset generation:

```bash
docker build -t rulesgen:local .
docker compose -f compose.yaml -f compose.opensandbox.yaml up --build -d opensandbox-server
RULESGEN_SANDBOX_BACKEND=opensandbox \
RULESGEN_OPENSANDBOX_DOMAIN=127.0.0.1:8090 \
RULESGEN_OPENSANDBOX_PROTOCOL=http \
RULESGEN_OPENSANDBOX_USE_SERVER_PROXY=false \
RULESGEN_OPENSANDBOX_IMAGE=rulesgen:local \
uv run uvicorn rulesgen.main:app --reload
```

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
    "source_text": "If job_level is 5 or higher, set bonus to 10 percent of salary.",
    "source_type": "natural_language",
    "target_column": "bonus",
    "schema_columns": ["salary", "job_level", "bonus"]
  }'
```

Look for:

- `dsl_candidate`
- `diagnostics`
- `prompt_audit`
- `explainability_trace`

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
    "schema_columns": ["order_id", "line_amount", "order_total"],
    "base_rows": [
      {"order_id": "A", "line_amount": 10},
      {"order_id": "A", "line_amount": 5},
      {"order_id": "B", "line_amount": 7}
    ],
    "rules": [
      {
        "target_column": "order_total",
        "expression": "group_sum(key=col(\"order_id\"), value=col(\"line_amount\"))"
      }
    ],
    "seed": 17
  }'
```

The response includes:

- `job_id`
- `status`
- `planned_column_sources`
- `diagnostics`

#### 5. Poll the job and inspect generated artifacts

```bash
curl -s "$BASE_URL/jobs/<job_id>"
```

The job response includes:

- `result.output_path` for the generated dataset
- `artifacts` entries for the dataset, manifest, diagnostics, and execution log
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
