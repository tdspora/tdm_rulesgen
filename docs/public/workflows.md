# Example Workflows

This page shows the two primary end-user workflows:

- Parse a `natural_language` rule, compile the DSL candidate, and preview it
  against one row.
- Upload a dataset, generate a target dataset, poll the resulting `job`, and
  download generated artifacts.

Start the local stack first with [Quick Start](getting-started.md), then set:

<!-- optional shell setup for local examples -->
<!-- skip: start -->
```bash
export BASE_URL=http://127.0.0.1:8000
```
<!-- skip: end -->

## Parse, Compile, Preview

Use this workflow when you want to inspect rule behavior before full dataset
generation.

### Parse a Natural-Language Rule

`POST /rules/parse` accepts either top-level rule fields or one rule embedded
in a schema row. For schema-embedded input, the target column is inferred from
the schema row `name`.

<!-- requires a running local rulesgen stack -->
<!-- skip: start -->
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
<!-- skip: end -->

Important response fields include:

- `dsl_candidate`: the translated DSL expression. Treat it as untrusted until
  compilation succeeds.
- `diagnostics`: structured feedback for parsing, translation, and validation.
- `prompt_audit` and `prompt_audits`: audit metadata for translation attempts.
- `metrics`: LLM request metrics when a real translation backend is used.
- `explainability_trace`: trace data connecting input, translation, and
  compiler behavior.

Supported schema row `source_type` values are `natural_language`, `dsl`, and
`domain_specific_language`.

### Compile the DSL Candidate

Use the parse response `dsl_candidate`, or submit a DSL expression directly.
The compile step validates the expression and returns a persisted
`compiled_rule` artifact.

<!-- requires a running local rulesgen stack -->
<!-- skip: start -->
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
<!-- skip: end -->

Save the returned `artifact_id`; the preview endpoint can use it without
resending the expression.

### Preview Against One Row

`POST /rules/preview` runs the compiled rule with a sample row and seed. Local
preview supports row-phase helpers only; aggregate helpers such as `group_sum`
and `group_count` are for dataset generation.

<!-- requires a running local rulesgen stack -->
<!-- skip: start -->
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
<!-- skip: end -->

Key response fields are `value`, `execution_mode`, and `diagnostics`.

## Upload, Generate, Poll, Download

Use this workflow when you want to apply rule-generated columns across a
dataset.

### Upload a Source File

`POST /datasets/uploads` stages a CSV or JSON file and returns a `file_id`.

<!-- requires a running local rulesgen stack and sample file -->
<!-- skip: start -->
```bash
UPLOAD_RESPONSE="$(
  curl -s "$BASE_URL/datasets/uploads" \
    -F "file=@samples/orders.csv;type=text/csv"
)"

export FILE_ID="$(echo "$UPLOAD_RESPONSE" | jq -r '.file_id')"
echo "FILE_ID=$FILE_ID"
```
<!-- skip: end -->

The upload response includes `file_id`, `format`, `row_count`, and `columns`.

### Submit a Generation Job

`POST /datasets/generate` creates a tracked generation `job`. Exactly one of
`base_rows` or `file_id` must be supplied. When `file_id` is used, the service
derives `row_count` from the uploaded file, so the request must not include
`row_count`.

<!-- requires a running local rulesgen stack and uploaded file -->
<!-- skip: start -->
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
<!-- skip: end -->

The response is metadata-only. It includes `job_id`, `status`,
`planned_column_sources`, `llm_metrics` when natural-language translation is
used, and `diagnostics`.

### Poll the Job

<!-- requires a running local rulesgen stack and submitted job -->
<!-- skip: start -->
```bash
curl -s "$BASE_URL/jobs/$JOB_ID"
```
<!-- skip: end -->

Poll until `status` is `succeeded` or `failed`. A succeeded job includes:

- `result.output_path`: generated dataset path on the `rulesgen` host.
- `artifacts`: dataset, manifest, diagnostics, and execution-log metadata.
- `diagnostics`: execution-path diagnostics.
- `llm_metrics`: translation metrics when natural-language rules were used.

The job response remains metadata-only; download endpoints retrieve file
contents.

### Download Generated Output

Download the generated dataset:

<!-- requires a completed local generation job -->
<!-- skip: start -->
```bash
curl -s "$BASE_URL/jobs/$JOB_ID/dataset" -o generated_rows.json
```
<!-- skip: end -->

Download a specific stored artifact from the same job:

<!-- requires a completed local generation job -->
<!-- skip: start -->
```bash
export ARTIFACT_ID="$(
  curl -s "$BASE_URL/jobs/$JOB_ID" \
    | jq -r '.artifacts[] | select(.kind == "input_manifest") | .artifact_id' \
    | head -n 1
)"
echo "ARTIFACT_ID=$ARTIFACT_ID"

curl -s "$BASE_URL/jobs/$JOB_ID/artifacts/$ARTIFACT_ID" -o artifact.bin
```
<!-- skip: end -->

By default, generated files are written under the configured local OSSFS root.
In the default local configuration that root is `.rulesgen-data/ossfs/`.

## Backend Behavior

Dataset generation uses the backend configured by `RULESGEN_SANDBOX_BACKEND`:

- `subprocess`: runs the shared dataset runner in a child Python process and
  stores manifests and outputs under the local OSSFS root.
- `opensandbox`: uploads the same manifest contract to an Alibaba
  OpenSandbox-managed container and downloads generated output back to the
  local OSSFS root.

See [Run Modes](run-modes.md) for local and OpenSandbox deployment choices.
