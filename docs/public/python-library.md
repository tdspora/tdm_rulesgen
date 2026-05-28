# Python Library

Use the `rulesgen` Python library when you want parsing, compilation,
preview, or generation behavior inside another Python process without running
the HTTP service.

## Install

Install the library package for in-process use:

<!-- installs packages in the active Python environment -->
<!-- skip: start -->
```bash
pip install rulesgen
```
<!-- skip: end -->

For a repository checkout managed by `uv`:

<!-- synchronizes the local development environment -->
<!-- skip: start -->
```bash
uv sync
```
<!-- skip: end -->

Install optional extras only when you need them:

- `rulesgen[api]`: FastAPI service dependencies.
- `rulesgen[guardrails]`: ML-backed prompt-injection guardrails.
- `rulesgen[guardrails-onnx]`: ML guardrails with ONNX runtime support.
- `rulesgen[databricks]`: Databricks Foundation Model APIs gateway.

## Compile and Preview

`compile_rule` validates a DSL expression and returns a `compiled_rule`.
`preview_rule` runs that compiled rule against one row and seed.

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

assert preview.value == 12000.0
assert preview.seed == 99
```

Preview is intended for row-level feedback. Aggregate helpers such as
`group_sum` and `group_count` are used during dataset generation, not local
preview.

## Parse Natural-Language Input

`parse_rule` accepts `natural_language` or DSL input. For
`natural_language`, the LLM gateway produces a `semantic_frame` and DSL
candidate; callers should still compile the DSL before treating it as
executable.

<!-- natural-language translation output depends on configured backend -->
<!-- skip: next -->
```python
from rulesgen import Settings, SourceType, parse_rule

settings = Settings(
    llm_gateway_backend="litellm",
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

For local smoke tests without a provider key, use the default stub backend:

```python
from rulesgen import Settings

settings = Settings(llm_gateway_backend="stub")

assert settings.llm_gateway_backend == "stub"
```

## Execute a Generation Plan

`execute_generation_plan` applies multiple compiled rules to rows in process.
Use it when an application already has source rows in memory and does not need
the HTTP job repository or download endpoints.

<!-- generation examples can write larger row payloads in real applications -->
<!-- skip: next -->
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

## Copy Job Artifacts

When the library shares the same local repositories as the API service, it can
copy completed job artifacts to another local path.

<!-- requires existing job and artifact repositories -->
<!-- skip: next -->
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

## Public Objects

The package exports the main functions and models needed by application
callers:

- `parse_rule`
- `compile_rule`
- `preview_rule`
- `execute_generation_plan`
- `download_job_dataset`
- `download_job_artifact`
- `Settings`
- `SourceType`
- `CompiledRule`
- `ExecutionPreview`
- `GenerationRun`
- `SemanticFrame`

Use [API Reference](api-reference.md) for HTTP request and response shapes.
