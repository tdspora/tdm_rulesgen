# API Reference

The `rulesgen` HTTP API exposes health checks, rule parsing and compilation,
preview execution, dataset upload and generation, job polling, and artifact
downloads. Start the service with [Quick Start](getting-started.md), then use
`http://127.0.0.1:8000` as the local base URL.

OpenAPI documentation is available when `RULESGEN_DOCS_ENABLED=true`:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Versioned Swagger UI: `http://127.0.0.1:8000/v1/docs`
- Versioned OpenAPI JSON: `http://127.0.0.1:8000/v1/openapi.json`

## Health

`GET /health/live`

Returns process liveness.

`GET /health/ready`

Returns readiness for serving requests.

## Rules

`POST /rules/parse`

Parses rule input into a `semantic_frame`, DSL candidate, diagnostics, and
translation metadata. A request can provide top-level rule fields or one
schema row with embedded `source_text` and `source_type`.

Common request fields:

- `source_text`: the natural-language rule or DSL expression.
- `source_type`: `natural_language`, `dsl`, or `domain_specific_language`.
- `target_column`: required for top-level natural-language requests.
- `table_name`: table context for translation and diagnostics.
- `schema`: schema rows, including rule-generated columns.
- `schema_columns`: lightweight column-name context for library-style calls.

Common response fields:

- `source_type`
- `intent`
- `target_column`
- `dependencies`
- `functions`
- `diagnostics`
- `dsl_candidate`
- `prompt_audit` and `prompt_audits`
- `metrics`
- `explainability_trace`

`POST /rules/compile`

Validates a DSL expression and persists a `compiled_rule` artifact.

<!-- mirrors CompileRuleRequest -->
```json
{
  "expression": "0.1 * col('salary') if col('job_level') >= 5 else 0",
  "target_column": "bonus"
}
```

The response includes `artifact_id`, `target_column`, `expression`,
`normalized_expression`, `dependencies`, `functions`, `helper_phases`,
`aggregate_helper`, `dsl_version`, and `source_type`.

`POST /rules/preview`

Runs a compiled rule against one row and seed. The request may reference an
existing `artifact_id` or provide an `expression` directly.

<!-- mirrors ExecuteRuleRequest -->
```json
{
  "artifact_id": "compiled-rule-id",
  "row": {
    "salary": 120000,
    "job_level": 6
  },
  "seed": 99,
  "references": {}
}
```

The response includes `value`, `execution_mode`, `seed`, `row`, `references`,
and `diagnostics`. The current preview execution mode is `local_preview`.

`POST /rules/execute`

Uses the same request and response shape as `/rules/preview`. It is available
for callers that use execute terminology while still running the local preview
path.

## Datasets

`POST /datasets/uploads`

Accepts a multipart file upload and stages a source dataset. The response
includes `file_id`, `filename`, `media_type`, `format`, `row_count`, and
`columns`.

<!-- requires a running local rulesgen stack and sample file -->
<!-- skip: start -->
```bash
curl -s "$BASE_URL/datasets/uploads" \
  -F "file=@samples/orders.csv;type=text/csv"
```
<!-- skip: end -->

`POST /datasets/generate`

Creates a dataset-generation `job`. Provide exactly one of:

- `file_id` for a staged upload.
- `base_rows` plus `row_count` for inline JSON rows.

When `file_id` is used, omit `row_count`; the service derives it from the
uploaded file.

The response includes `job_id`, `status`, `row_count`,
`planned_column_sources`, `diagnostics`, and `llm_metrics` when
natural-language translation is used.

## Jobs and Downloads

`POST /jobs`

Creates a job directly. Most dataset-generation callers should use
`POST /datasets/generate`, which plans the dataset request and creates the job
for them.

`GET /jobs/{job_id}`

Returns job metadata including:

- `job_id`
- `kind`
- `status`
- `payload`
- `result`
- `error`
- `diagnostics`
- `artifacts`
- `llm_metrics`

Job status values are `pending`, `running`, `succeeded`, and `failed`.

`GET /jobs/{job_id}/dataset`

Downloads the generated dataset for a completed job.

`GET /jobs/{job_id}/artifacts/{artifact_id}`

Downloads a specific stored artifact. Artifact kinds include
`input_manifest`, `dataset`, `execution_log`, `diagnostics`, and
`compiled_rule`.

## Schema Rows

Schema rows describe source and rule-generated columns. Common fields are:

- `name`
- `type`
- `nullable`
- `source`: `syngen`, `rule`, or `base`
- `source_text`: rule text for rule-generated columns
- `source_type`: `natural_language`, `dsl`, or `domain_specific_language`
- `artifact_id`
- `notes`

## Problem Details

API errors use the Problem Details envelope with
`application/problem+json`. The base URL for problem `type` values is
configured by `RULESGEN_PROBLEM_BASE_URL`.

<!-- mirrors Problem Details error responses -->
```json
{
  "type": "https://docs.rulesgen.local/problems/validation_failed",
  "title": "Validation failed",
  "status": 422,
  "detail": "Request validation failed.",
  "instance": "/rules/parse",
  "code": "validation_failed",
  "request_id": "request-id",
  "errors": []
}
```

Common error codes include `validation_failed`, `dsl_parse_failed`,
`dsl_validation_failed`, `guardrail_blocked`, `request_validation_failed`,
`unauthorized`, `forbidden`, `not_found`, `rule_not_found`, `job_not_found`,
and `file_not_found`.

Guardrail-blocked responses do not expose scanner names, matched categories,
or risk scores to API callers.
