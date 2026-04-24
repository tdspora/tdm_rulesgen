# Quick Start

`rulesgen` is easiest to evaluate through the Docker Compose stack.

## Prerequisites

- Docker
- `docker compose`
- `curl`
- `jq`
- One LLM provider credential such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `GEMINI_API_KEY`, or `AZURE_API_KEY`

## Start the stack

```bash
./scripts/run_stack.sh
```

If the required provider credential is not already set, the script prompts for
it.

## Service endpoints

- API root: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Versioned OpenAPI docs: `http://127.0.0.1:8000/v1/docs`

## Verify readiness

```bash
curl -s http://127.0.0.1:8000/health/ready
```

## What to do next

- Follow the end-to-end parse, compile, preview, and generation examples in
  the repository `README.md`.
- Review the [Domain Vocabulary](../domain-dictionary.md) before changing
  pipeline terms or contributor-facing docs.
- Use [Repository Docs](repository-docs.md) for the longer design and
  contributor material that still lives in the repository.
