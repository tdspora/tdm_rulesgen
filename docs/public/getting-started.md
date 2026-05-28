# Quick Start

The fastest way to evaluate `rulesgen` is the Docker Compose stack started by
`./scripts/run_stack.sh`. It starts the API, OpenSandbox support, and an LLM
translation path. If no provider credential is present, the script falls back
to the built-in stub translation backend so the stack can still run locally.

## Prerequisites

- Docker
- `docker compose`
- `curl`
- `jq`
- Optional: one LLM provider credential such as `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `AZURE_API_KEY`

## Start the stack

<!-- starts local containers and may build images -->
<!-- skip: start -->
```bash
./scripts/run_stack.sh
```
<!-- skip: end -->

When no provider key is set, the script sets
`RULESGEN_LLM_GATEWAY_BACKEND=stub`. The stub backend is useful for local
smoke tests and API walkthroughs. Set a provider key when you want real
natural-language translation.

## Service endpoints

- API root: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Versioned Swagger UI: `http://127.0.0.1:8000/v1/docs`

## Verify readiness

<!-- requires a running local rulesgen stack -->
<!-- skip: start -->
```bash
curl -s http://127.0.0.1:8000/health/ready
```
<!-- skip: end -->

The readiness response confirms that the API process is accepting requests.

## Set a base URL

The workflow examples use `BASE_URL` for readability.

<!-- optional shell setup for the examples in workflows.md -->
<!-- skip: start -->
```bash
export BASE_URL=http://127.0.0.1:8000
```
<!-- skip: end -->

## What to do next

- Follow [Example Workflows](workflows.md) to parse, compile, preview,
  generate, poll, and download artifacts.
- Use [API Reference](api-reference.md) when integrating with the HTTP API.
- Use [Python Library](python-library.md) when embedding `rulesgen` directly
  in another Python process.
- Review [Configuration](configuration.md), [Run Modes](run-modes.md), and
  [Safety Guardrails](safety-guardrails.md) before operating the service
  beyond a local evaluation.
- Use [Repository Docs](repository-docs.md) for the longer design and
  contributor material that still lives in the repository.
