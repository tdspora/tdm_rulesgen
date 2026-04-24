# rulesgen

`rulesgen` is a secure rule-processing service for synthetic data workflows.

It converts natural-language instructions into a restricted DSL, validates and compiles that DSL into an executable artifact, lets you preview rule behavior locally, and can generate datasets through either a local subprocess executor or an OpenSandbox-backed runtime.

The project is designed for teams that need:
- natural-language rule authoring
- deterministic validation and compilation
- safe local previews
- optional sandboxed execution for full dataset generation

## What it does

`rulesgen` supports a staged rule lifecycle:

1. **Parse** natural language into an untrusted intermediate form (`semantic_frame`) and DSL candidate
2. **Compile** the DSL into a validated executable artifact (`compiled_rule`)
3. **Preview** rule execution against a sample row
4. **Generate** datasets using a local or sandbox-backed execution path

This separation is intentional. Natural-language output is never trusted directly. A rule only becomes executable after validation and compilation succeed.

---

## Quick start

The fastest way to get started is with Docker Compose.

### Prerequisites

- Docker
- `docker compose`
- `curl`
- `jq`

### Start the stack

The default setup runs:
- `rulesgen`
- OpenSandbox
- an LLM-backed translation path through LiteLLM when provider credentials are present
- the built-in stub translation backend when provider credentials are absent

Optional provider credentials for LiteLLM (examples):
  - `OPENAI_API_KEY` (OpenAI / OpenAI-compatible)
  - `ANTHROPIC_API_KEY`
  - `GEMINI_API_KEY`
  - `AZURE_API_KEY` (Azure OpenAI; often used with `AZURE_API_VERSION`)
`./scripts/run_stack.sh` now falls back to `RULESGEN_LLM_GATEWAY_BACKEND=stub` when none of these credentials are set. Docker Compose still forwards the provider variables into the `rulesgen` container via `${VAR:-}` entries in the compose files.


Start the stack:

```bash
./scripts/run_stack.sh
```

If a provider key is not set, the stack still starts and uses the stub translation backend.

### Service endpoints

Once the stack is up, the API is available at:

* `http://127.0.0.1:8000`
* `http://127.0.0.1:8000/docs` for OpenAPI documentation, when enabled

### Verify readiness

```bash
curl -s http://127.0.0.1:8000/health/ready
```

### Run the example workflows

In a new terminal:

```bash
export BASE_URL=http://127.0.0.1:8000
```

Then continue with the two workflows below.

---

## Example workflows

## 1. Parse → Compile → Preview

This workflow shows the safest path from natural-language input to executable rule behavior.

### Step 1: Parse a natural-language instruction

The parse endpoint returns:

* inferred intent
* a candidate DSL expression
* diagnostics
* prompt-audit metadata
* explainability and metrics data

At this stage, the output is still **untrusted**.

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

Important fields in the response:

* `dsl_candidate`
* `diagnostics`
* `prompt_audit`
* `metrics`
* `explainability_trace`

For schema-embedded rule requests, the target column is inferred from the schema row `name`. Supported row-level `source_type` values are:

* `natural_language`
* `domain_specific_language`

### Step 2: Compile the DSL into a validated rule artifact

Use the `dsl_candidate` from the parse response, or submit a DSL expression directly.

```bash
COMPILE_RESPONSE="$(
  curl -s "$BASE_URL/rules/compile" \
    -H "Content-Type: application/json" \
    --data-binary @- <<'EOF'
{
  "expression": "0.1 * col('salary') if col('job_level') >= 5 else 0",
  "target_column": "bonus"
}
EOF
)"

export ARTIFACT_ID="$(echo "$COMPILE_RESPONSE" | jq -r '.artifact_id')"
echo "ARTIFACT_ID=$ARTIFACT_ID"
```

Save the returned `artifact_id`. You will use it in the preview step.

### Step 3: Preview the rule against a sample row

The preview endpoint executes the compiled rule locally and supports row-phase helpers only.

```bash
curl -s "$BASE_URL/rules/preview" \
  -H "Content-Type: application/json" \
  --data-binary @- <<EOF
{
  "artifact_id": "$ARTIFACT_ID",
  "row": {
    "salary": 120000,
    "job_level": 6
  },
  "seed": 99
}
EOF
```

Key fields in the response:

* `value`
* `execution_mode`
* `diagnostics`

---

## 2. Upload a dataset file → Generate a dataset → Poll the job → Inspect artifacts

This workflow shows full dataset generation, including staged file upload, job tracking, and artifact retrieval.

### Step 1: Upload a source file

```bash
UPLOAD_RESPONSE="$(
  curl -s "$BASE_URL/datasets/uploads" \
    -F "file=@samples/orders.csv;type=text/csv"
)"

export FILE_ID="$(echo "$UPLOAD_RESPONSE" | jq -r '.file_id')"
echo "FILE_ID=$FILE_ID"
```

The response includes:

* `file_id`
* `format`
* `row_count`
* `columns`

Save the returned `file_id`. You will use it in the generation request.

### Step 2: Submit a generation job

```bash
GENERATE_RESPONSE="$(
  curl -s "$BASE_URL/datasets/generate" \
    -H "Content-Type: application/json" \
    --data-binary @- <<EOF
{
  "file_id": "$FILE_ID",
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
}
EOF
)"

export JOB_ID="$(echo "$GENERATE_RESPONSE" | jq -r '.job_id')"
echo "JOB_ID=$JOB_ID"
```

Exactly one of `base_rows` or `file_id` must be provided:

* use `file_id` for staged CSV or JSON uploads
* use `base_rows` plus `row_count` for inline JSON rows

When `file_id` is used, `row_count` is derived from the uploaded file and must not be supplied.

The generation response includes:

* `job_id`
* `status`
* `planned_column_sources`
* `llm_metrics`, when natural-language translation is used
* `diagnostics`

This response is metadata-only. It does not embed the generated row payload.

### Step 3: Poll the job

```bash
curl -s "$BASE_URL/jobs/$JOB_ID"
```

The job response includes:

* `result.output_path` for the generated dataset on the `rulesgen` host
* `artifacts` for the dataset, manifest, diagnostics, and execution log
* `llm_metrics` for the translation session, when applicable
* `diagnostics` from the execution path

This JSON response remains metadata-only. Use the download endpoints below to retrieve file contents.

### Step 4: Download the generated dataset

```bash
curl -s "$BASE_URL/jobs/$JOB_ID/dataset" -o generated_rows.json
```

To download a specific stored artifact from the same job, select an `artifact_id` from
`GET /jobs/$JOB_ID` and export it (example: download the input manifest):

```bash
export ARTIFACT_ID="$(
  curl -s "$BASE_URL/jobs/$JOB_ID" \
    | jq -r '.artifacts[] | select(.kind == "input_manifest") | .artifact_id' \
    | head -n 1
)"
echo "ARTIFACT_ID=$ARTIFACT_ID"

curl -s "$BASE_URL/jobs/$JOB_ID/artifacts/$ARTIFACT_ID" -o artifact.bin
```

By default, generated files are written under the local OSSFS root:

```text
.rulesgen-data/ossfs/
```

Execution backend behavior depends on configuration:

* `RULESGEN_SANDBOX_BACKEND=subprocess`
  Uses the local subprocess dataset executor

* `RULESGEN_SANDBOX_BACKEND=opensandbox`
  Uploads the same manifest to an Alibaba OpenSandbox-managed container, then downloads the generated dataset back into the local OSSFS root

---

## Configuration

## Optional

### `OPENAI_API_KEY`

Used when you want LiteLLM to call OpenAI or an OpenAI-compatible endpoint.

If you use `./scripts/run_stack.sh` without any provider credentials, the script starts the stack with the stub translation backend instead.

## Optional

### `RULESGEN_LLM_MODEL_NAME`

Overrides the default model defined in Compose.

### `RULESGEN_LLM_GATEWAY_URL`

Leave unset to use the default OpenAI-compatible endpoint:

```text
https://api.openai.com/v1
```

Set this only if you are routing through an OpenAI-compatible proxy.

## Where configuration is loaded from

### Docker Compose

Configuration comes from:

* `compose.yaml`
* `compose.opensandbox.yaml`
* your shell environment

### Host-run mode

Configuration comes from:

* `.env`
* your shell environment

See `.env.example` for the supported `RULESGEN_*` settings.

---

## Run modes

## Recommended: Docker Compose with OpenSandbox

This is the mode used by `./scripts/run_stack.sh`.

```bash
export OPENAI_API_KEY=your-openai-key
docker compose -f compose.yaml -f compose.opensandbox.yaml up --build
```

Without any provider credentials:

```bash
./scripts/run_stack.sh
```

Stop the stack:

```bash
./scripts/run_stack.sh down
```

## Docker Compose without OpenSandbox

This mode uses the local subprocess executor only.

```bash
docker compose up --build
```

If you want Docker Compose to start without provider credentials, set `RULESGEN_LLM_GATEWAY_BACKEND=stub` in your shell before running `docker compose up --build`.

## Host-run API with Compose-run OpenSandbox

This mode is useful for contributors who want to run the API locally while keeping OpenSandbox in Docker.

Start OpenSandbox:

```bash
docker compose -f compose.yaml -f compose.opensandbox.yaml up --build -d opensandbox-server
```

Start `rulesgen` on the host:

```bash
uv sync --extra api --extra dev
docker build -t rulesgen:local .
export OPENAI_API_KEY=your-openai-key  # omit this and set RULESGEN_LLM_GATEWAY_BACKEND=stub to use the stub backend
RULESGEN_SANDBOX_BACKEND=opensandbox \
RULESGEN_OPENSANDBOX_DOMAIN=127.0.0.1:8090 \
RULESGEN_OPENSANDBOX_PROTOCOL=http \
RULESGEN_OPENSANDBOX_USE_SERVER_PROXY=false \
RULESGEN_OPENSANDBOX_IMAGE=rulesgen:local \
uv run uvicorn rulesgen.main:app --reload
```

---

## Using rulesgen as a Python library

You can use `rulesgen` without running the API service.

The package exposes high-level entry points for parsing, compilation, preview, and in-process execution.

### Compile and preview a rule locally

```python
from rulesgen import compile_rule, preview_rule

compiled = compile_rule(
    '0.1 * col("salary") if col("job_level") >= 5 else 0',
    target_column="bonus",
)

preview = preview_rule(
    compiled,
    row={"salary": 120000, "job_level": 6},
    seed=99,
)

print(preview.value)
```

### Parse a natural-language rule

```python
from rulesgen import Settings, SourceType, parse_rule

settings = Settings(
    llm_gateway_backend="litellm",  # or: "http" / "stub"
    llm_model_name="gpt-4",
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

### Execute multiple compiled rules in-process

```python
from rulesgen import Settings, compile_rule, execute_generation_plan

settings = Settings()

rows = [
    {"order_id": "A", "line_amount": 10},
    {"order_id": "A", "line_amount": 5},
    {"order_id": "B", "line_amount": 7},
]

compiled_rules = [
    compile_rule(
        'col("line_amount") * 2',
        target_column="line_amount_x2",
        settings=settings,
    ),
    compile_rule(
        'group_sum(key=col("order_id"), value=col("line_amount"))',
        target_column="order_total",
        settings=settings,
    ),
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

### Copy a generated artifact for a completed job

When the library shares the same local repositories as the API service, you can copy
completed job artifacts to another local path:

```python
from rulesgen import Settings, download_job_artifact, download_job_dataset

settings = Settings(
    jobs_repository_dir=".rulesgen-data/jobs",
    artifacts_repository_dir=".rulesgen-data/artifacts",
    ossfs_root_dir=".rulesgen-data/ossfs",
)

dataset_copy = download_job_dataset(
    "job-id",
    destination="downloads/generated_rows.json",
    settings=settings,
)

manifest_copy = download_job_artifact(
    "job-id",
    "artifact-id",
    destination="downloads/sandbox_manifest.json",
    settings=settings,
)

print(dataset_copy)
print(manifest_copy)
```

---

## API reference

### Health

* `GET /health/live`
* `GET /health/ready`

### Rules

* `POST /rules/parse`
* `POST /rules/compile`
* `POST /rules/preview`
* `POST /rules/execute`

### Datasets and jobs

* `POST /datasets/uploads`
* `POST /datasets/generate`
* `POST /jobs`
* `GET /jobs/{job_id}`
* `GET /jobs/{job_id}/dataset`
* `GET /jobs/{job_id}/artifacts/{artifact_id}`

---

## Architecture summary

The HTTP layer is intentionally thin.

* routers depend on services
* services depend on compiler and repository interfaces
* execution is limited to validated AST artifacts with a restricted runtime surface

Natural-language parsing always produces an untrusted `semantic_frame` and DSL candidate first. Only validated DSL can be compiled into an executable artifact.

Execution paths are separated by purpose:

* **preview execution** uses the local preview executor and supports row-phase helpers
* **dataset generation** uses either the subprocess executor or the OpenSandbox adapter
* both generation modes preserve the same manifest and artifact contract under the configured OSSFS root

---

## What’s included

* production-oriented ASGI application skeleton under `src/rulesgen/`
* structured logging and request context propagation
* RFC 9457 problem-details responses
* versioned API modules for health, rules, datasets, and jobs
* restricted DSL compilation based on Python AST validation
* filesystem-backed repositories for rules, jobs, prompt audits, and artifacts
* local preview execution
* subprocess dataset execution
* optional OpenSandbox integration for sandboxed dataset generation
* tests, CI, and container build support

---

## Development

Install development dependencies:

```bash
uv sync --extra api --extra dev
```

Useful commands:

```bash
uv sync --extra api --extra dev
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy src
uv run pip-audit
```

---

## Documentation

The project documentation site uses MkDocs with the Material theme and sources
its published pages from `docs/`.

For a full contributor environment with the docs toolchain enabled:

```bash
uv sync --extra api --extra dev --extra docs --locked
uv run mkdocs serve
```

To build the site the same way as the GitHub Pages workflow:

```bash
uv run mkdocs build --strict
```

Once GitHub Pages is configured to deploy from GitHub Actions, the published
site lives at `https://tdspora.github.io/tdm_rulesgen/`.

The Pages site is intentionally smaller than the full set of repository docs.
Longer design and contributor references remain in the repository and are
linked from the published site.

---

## Release process

Pushes to `main` run CI, build the wheel and sdist, create the GitHub Release via semantic-release, attach release artifacts to that release, publish the same distributions to PyPI, and build/push a Docker image to Docker Hub.

Before enabling automated releases, configure these repository secrets:

- `DEPLOY_KEY` for the SSH deploy key that semantic-release uses to push version bump commits and tags.
- `PYPI_TOKEN` for a PyPI API token scoped to the `rulesgen` project.
- `DOCKER_HUB_USER` for the Docker Hub namespace that owns the published `rulesgen` image.
- `DOCKER_HUB_TOKEN` for a Docker Hub access token with permission to push images for that namespace.

The PyPI and Docker publishing jobs both check out the GitHub release tag created by semantic-release and verify that `project.version` matches the released semver before publishing.

When a release is published, the workflow pushes `DOCKER_HUB_USER/rulesgen` with `latest`, `vX.Y.Z`, and `X.Y.Z` tags, while PyPI receives distributions built from that same tagged source.

Before the first automated release, create a baseline tag that matches `project.version` in `pyproject.toml`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

If branch protection requires pull requests on `main`, allow the GitHub Actions app to bypass that requirement so semantic-release can push its version bump commit and publish release assets.

The script below applies the recommended repository and branch-protection settings and prints the one remaining manual UI step:

```text
scripts/configure-github-repo-oss.sh
```

---

## Project guidance

* Domain vocabulary for contributors and agents lives in `docs/domain-dictionary.md`
* Cursor rules for this repository live in `.cursor/rules/`

---

## License

This project is licensed under the **Apache License 2.0**. See [`LICENSE`](LICENSE) for the full text and [`NOTICE`](NOTICE) for copyright attribution.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). This project follows the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Report security issues according to [`SECURITY.md`](SECURITY.md).
