# Safety Guardrails

`rulesgen` treats all natural-language rule input as untrusted. Before a
`natural_language` rule reaches the LLM gateway, guardrails scan it for prompt
injection and jailbreak attempts.

If a request is blocked, the API returns `422 Unprocessable Entity` with
`code: "guardrail_blocked"` in the standard Problem Details envelope. The
response body does not expose matched categories, scanner names, or risk
scores to the caller. Operators can review the internal prompt-audit record
for the blocked attempt.

## Backends

`RULESGEN_GUARDRAILS_BACKEND=heuristic`

The default backend. It uses local regex-style checks for instruction
override, system-prompt leak, role override, code escape, and delimiter
injection patterns. It has no model downloads and no network egress.

`RULESGEN_GUARDRAILS_BACKEND=llm_guard`

An optional ML-backed backend using `llm-guard`. Install the guardrails extra
before enabling it. `RULESGEN_GUARDRAILS_MODEL_ID` can point to an approved
HuggingFace identifier or to a local model path, and
`RULESGEN_GUARDRAILS_MODEL_CACHE_DIR` controls where model files are cached.

`RULESGEN_GUARDRAILS_BACKEND=http`

Calls a customer-owned classification endpoint. This backend is designed for
Databricks Model Serving or a private classifier service. It supports `none`,
`bearer`, and `databricks_sdk` auth modes.

`RULESGEN_GUARDRAILS_BACKEND=off`

Disables guardrails. Use only in isolated test environments.

## Configure the Heuristic Backend

The heuristic backend is enabled by default.

<!-- environment setup for a local shell session -->
<!-- skip: start -->
```bash
export RULESGEN_GUARDRAILS_ENABLED=true
export RULESGEN_GUARDRAILS_BACKEND=heuristic
```
<!-- skip: end -->

## Configure the LLM Guard Backend

Install the optional extra, then select the backend and threshold:

<!-- installs optional guardrail dependencies -->
<!-- skip: start -->
```bash
pip install 'rulesgen[guardrails]'

export RULESGEN_GUARDRAILS_BACKEND=llm_guard
export RULESGEN_GUARDRAILS_THRESHOLD=0.5
export RULESGEN_GUARDRAILS_MODEL_ID=ProtectAI/deberta-v3-base-prompt-injection-v2
export RULESGEN_GUARDRAILS_MODEL_CACHE_DIR=/Volumes/catalog/schema/volume/hf-cache
```
<!-- skip: end -->

Use `rulesgen[guardrails-onnx]` when your deployment has approved ONNX runtime
usage for CPU inference.

## Configure the HTTP Backend

Use the HTTP backend when a customer-owned service performs classification.
The endpoint and auth environment variable name are configuration values; do
not hardcode credential values.

<!-- environment setup for a customer-owned classifier endpoint -->
<!-- skip: start -->
```bash
export RULESGEN_GUARDRAILS_BACKEND=http
export RULESGEN_GUARDRAILS_HTTP_ENDPOINT=https://workspace.example.com/serving-endpoints/classifier/invocations
export RULESGEN_GUARDRAILS_HTTP_AUTH_MODE=bearer
export RULESGEN_GUARDRAILS_HTTP_AUTH_ENV_VAR=DATABRICKS_TOKEN
export RULESGEN_GUARDRAILS_HTTP_THRESHOLD=0.5
export RULESGEN_GUARDRAILS_HTTP_RESPONSE_SCORE_PATH=predictions.0.score
```
<!-- skip: end -->

For Databricks SDK authentication, install the Databricks extra and use:

<!-- environment setup for Databricks SDK auth -->
<!-- skip: start -->
```bash
export RULESGEN_GUARDRAILS_HTTP_AUTH_MODE=databricks_sdk
export RULESGEN_GUARDRAILS_HTTP_DATABRICKS_HOST_ENV_VAR=DATABRICKS_HOST
```
<!-- skip: end -->

## Prompt Audit Behavior

A blocked request still emits a prompt-audit record with internal scanner
metadata. API callers receive only the Problem Details response. This keeps
operator review possible without teaching callers which detection category or
risk score matched.

## Related Configuration

See [Configuration](configuration.md) for the full settings list and
[Databricks Models](databricks.md) for Databricks-hosted gateway behavior.
