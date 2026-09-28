# Configuration

`rulesgen` uses Pydantic settings with the `RULESGEN_` environment-variable
prefix. In host-run mode, settings are loaded from `.env` and the shell
environment. In Docker Compose mode, settings come from `compose.yaml`,
`compose.opensandbox.yaml`, and the shell environment.

See the repository
[`.env.example`](https://github.com/tdspora/tdm_rulesgen/blob/main/.env.example)
for a local template.

## Application Settings

Core service settings:

- `RULESGEN_APP_NAME`
- `RULESGEN_APP_VERSION`
- `RULESGEN_ENV`
- `RULESGEN_LOG_LEVEL`
- `RULESGEN_DOCS_ENABLED`
- `RULESGEN_PROBLEM_BASE_URL`

`RULESGEN_DOCS_ENABLED=true` enables the built-in OpenAPI pages at `/docs`,
`/redoc`, and `/openapi.json`, plus the versioned docs endpoints under
`/v1/docs` and `/v1/openapi.json`.

## Auth and HTTP Edge

Authentication is disabled by default for local evaluation:

- `RULESGEN_AUTH_ENABLED=false`
- `RULESGEN_API_KEY=change-me`

When `RULESGEN_AUTH_ENABLED=true`, callers provide the API key through the
`X-API-Key` header.

HTTP edge settings:

- `RULESGEN_CORS_ALLOW_ORIGINS`
- `RULESGEN_TRUSTED_HOSTS`

Both can be supplied as comma-separated values or JSON-style lists.

## DSL Limits

The compiler validates DSL expressions against size and depth limits:

- `RULESGEN_DSL_MAX_LENGTH`
- `RULESGEN_DSL_MAX_DEPTH`
- `RULESGEN_DSL_MAX_NODES`

These limits protect parser and validator behavior for untrusted rule input.

Evaluation is bounded separately by `RULESGEN_DSL_MAX_VALUE_LENGTH` (default
`1048576`). No value a rule produces during preview or dataset generation may
be larger than this: operator results, helper results such as `concat(...)`,
and the final rule result. Sizes follow the printed form of a value: text
counts one unit per character, numbers count their digits, other values count
the length of their printed form, and a list or tuple counts one unit plus,
for each element, the element's size and one separator unit. `+`, `*`, list
and tuple literals, `concat(...)`, `lower(...)`, and `upper(...)` are checked
before the value is built or printed; other results are checked right after
they are produced.

When a limit is exceeded, a preview request fails with a `validation_failed`
Problem Details response, and a dataset generation job finishes with status
`failed` and the reason in `error`. `regex(...)` accepts at most 256 digits;
larger counts fail at compile time with `dsl_validation_failed` and the
`dsl_regex_too_long` diagnostic.

## Local Storage

Generated files, uploads, rules, jobs, artifacts, audits, and semantic-cache
data are local runtime outputs. Keep them out of source control.

Storage settings:

- `RULESGEN_DATA_DIR`
- `RULESGEN_RULES_REPOSITORY_DIR`
- `RULESGEN_JOBS_REPOSITORY_DIR`
- `RULESGEN_ARTIFACTS_REPOSITORY_DIR`
- `RULESGEN_UPLOADS_REPOSITORY_DIR`
- `RULESGEN_AUDITS_REPOSITORY_DIR`
- `RULESGEN_OSSFS_ROOT_DIR`
- `RULESGEN_LLM_SEMANTIC_CACHE_DIR`

The default local output tree is under `.rulesgen-data/`.

In the Docker image, the entrypoint starts as root, creates these directories,
and gives them to the unprivileged `appuser` before it starts the API. It
skips a directory whose path resolves through a symbolic link and prints a
warning, and it does not change the owner of hard-linked files. Mount volumes
directly at the configured paths, or set the paths to their resolved
locations.

## Execution Backend

Dataset generation uses `RULESGEN_SANDBOX_BACKEND`:

- `subprocess`: the default child-process dataset executor.
- `opensandbox`: the Alibaba OpenSandbox adapter.

Shared sandbox settings:

- `RULESGEN_SANDBOX_BACKEND`
- `RULESGEN_SANDBOX_WORKSPACE_DIR`
- `RULESGEN_SANDBOX_TIMEOUT_SECONDS`
- `RULESGEN_SANDBOX_PYTHON_EXECUTABLE`
- `RULESGEN_SANDBOX_MAX_MEMORY_MB`

`RULESGEN_SANDBOX_MAX_MEMORY_MB` (default `2048`) is how much additional
address space the dataset generation process may allocate after it starts,
with either the `subprocess` or the `opensandbox` backend. It is enforced on
Linux. On other platforms the job runs without it and reports a
`sandbox_memory_limit_unavailable` warning diagnostic. A job that exceeds the
limit fails instead of exhausting host memory. Set it to `0` to disable the
limit.

The subprocess dataset executor starts its child process with an allowlisted
environment: path, home, locale, time-zone, temporary-directory,
dynamic-linker, Windows system, and Python interpreter variables. It also sets
`LITELLM_LOCAL_MODEL_COST_MAP=True`, so the child never downloads litellm's
model cost map. Provider keys and other credentials in the API process
environment are not passed to the child. The child still runs as the same
operating-system user as the API, so the subprocess dataset executor is not a
full isolation boundary.

OpenSandbox settings:

- `RULESGEN_OPENSANDBOX_DOMAIN`
- `RULESGEN_OPENSANDBOX_PROTOCOL`
- `RULESGEN_OPENSANDBOX_API_KEY`
- `RULESGEN_OPENSANDBOX_REQUEST_TIMEOUT_SECONDS`
- `RULESGEN_OPENSANDBOX_USE_SERVER_PROXY`
- `RULESGEN_OPENSANDBOX_IMAGE`
- `RULESGEN_OPENSANDBOX_TTL_SECONDS`
- `RULESGEN_OPENSANDBOX_READY_TIMEOUT_SECONDS`
- `RULESGEN_OPENSANDBOX_WORKSPACE_DIR`

See [Run Modes](run-modes.md) for example combinations.

## LLM Gateway

The LLM gateway translates `natural_language` input into a `semantic_frame`
and DSL candidate. Configure it with:

- `RULESGEN_LLM_GATEWAY_BACKEND`: `stub`, `http`, or `litellm`.
- `RULESGEN_LLM_GATEWAY_URL`: optional OpenAI-compatible gateway URL.
- `RULESGEN_LLM_GATEWAY_TIMEOUT_SECONDS`
- `RULESGEN_LLM_PROMPT_TEMPLATE_VERSION`
- `RULESGEN_LLM_MODEL_NAME`
- `RULESGEN_LLM_TEMPERATURE`
- `RULESGEN_LLM_EXTRA_COMPLETION_PARAMS`
- `RULESGEN_LLM_FEEDBACK_MAX_ATTEMPTS`
- `RULESGEN_LLM_PROVIDER`: `auto`, `openai`, `anthropic`, `gemini`,
  `azure`, or `databricks`.

Provider keys such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`, and `AZURE_API_KEY` are read by the provider SDKs or gateway
client. They are credential values at runtime and must never be committed.

`RULESGEN_LLM_TEMPERATURE` accepts `null` or an empty string to omit the
temperature parameter entirely. Use `RULESGEN_LLM_EXTRA_COMPLETION_PARAMS` for
model-specific JSON options such as maximum-token or reasoning controls.

The `stub` backend only matches its templates against natural-language rules
of up to 1000 characters and reports longer rules as unsupported.
Independently of the backend, the HTTP API rejects a rule `source_text` longer
than 4000 characters with `request_validation_failed`.

## Databricks Gateway Settings

The Databricks gateway is selected by `RULESGEN_LLM_PROVIDER=databricks`, or
by provider auto-detection when Databricks runtime variables are present and
the Databricks extra is installed.

Databricks environment-variable name settings:

- `RULESGEN_DATABRICKS_HOST_ENV_VAR`
- `RULESGEN_DATABRICKS_TOKEN_ENV_VAR`

Their default values point to the standard Databricks SDK environment
variable names. The credential values themselves are resolved by the
Databricks SDK auth chain.

See [Databricks Models](databricks.md) for setup examples.

## Semantic Cache

Semantic-cache settings:

- `RULESGEN_LLM_SEMANTIC_CACHE_ENABLED`
- `RULESGEN_LLM_SEMANTIC_CACHE_DIR`
- `RULESGEN_LLM_SEMANTIC_CACHE_SIMILARITY_THRESHOLD`
- `RULESGEN_LLM_SEMANTIC_CACHE_EMBEDDING_DIMENSION`

Cache entries are scoped by prompt version, model, table, schema fingerprint,
and requested targets.

A cache hit also requires exactly the same prompt text, including whitespace.
Embedding similarity alone never reuses another prompt's translation, because
one word such as "higher" or "lower" can invert a rule.
`RULESGEN_LLM_SEMANTIC_CACHE_SIMILARITY_THRESHOLD` remains an additional
gate.

Cache files store a SHA-256 digest of each prompt instead of the prompt text,
next to the cached DSL translation and a hashed embedding of the prompt. When
the API starts and uses the semantic cache, it rewrites cache files from
earlier versions, which stored the prompt text, to digests. It logs a warning
for each file it cannot read and leaves that file in place. If the API does
not use the semantic cache, for example because it is turned off, delete the
`RULESGEN_LLM_SEMANTIC_CACHE_DIR` directory to remove prompt text that earlier
versions stored.

## Guardrails

Guardrails scan natural-language rule input before it reaches the LLM gateway.

Core settings:

- `RULESGEN_GUARDRAILS_ENABLED`
- `RULESGEN_GUARDRAILS_BACKEND`
- `RULESGEN_GUARDRAILS_THRESHOLD`
- `RULESGEN_GUARDRAILS_MATCH_TYPE`
- `RULESGEN_GUARDRAILS_MODEL_CACHE_DIR`
- `RULESGEN_GUARDRAILS_MODEL_ID`
- `RULESGEN_GUARDRAILS_BLOCK_MESSAGE`

HTTP scanner settings:

- `RULESGEN_GUARDRAILS_HTTP_ENDPOINT`
- `RULESGEN_GUARDRAILS_HTTP_AUTH_MODE`
- `RULESGEN_GUARDRAILS_HTTP_AUTH_ENV_VAR`
- `RULESGEN_GUARDRAILS_HTTP_DATABRICKS_HOST_ENV_VAR`
- `RULESGEN_GUARDRAILS_HTTP_TIMEOUT_SECONDS`
- `RULESGEN_GUARDRAILS_HTTP_THRESHOLD`
- `RULESGEN_GUARDRAILS_HTTP_REQUEST_FIELD`
- `RULESGEN_GUARDRAILS_HTTP_RESPONSE_SCORE_PATH`

See [Safety Guardrails](safety-guardrails.md) for backend behavior.

## Local Example

This example runs local translation through the stub backend and uses the
subprocess dataset executor.

<!-- environment setup for a local shell session -->
<!-- skip: start -->
```bash
export RULESGEN_LLM_GATEWAY_BACKEND=stub
export RULESGEN_SANDBOX_BACKEND=subprocess
export RULESGEN_DOCS_ENABLED=true
```
<!-- skip: end -->
