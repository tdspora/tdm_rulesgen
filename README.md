# rulesgen

`rulesgen` is a secure rule-processing service for synthetic data workflows.
It accepts rule input as either `natural_language` or a restricted DSL,
translates `natural_language` requests into an untrusted `semantic_frame` plus
DSL candidate, validates DSL into a `compiled_rule`, supports local
`execution_preview`, and can execute full dataset generation as a tracked
`job`.

Natural-language output is never trusted directly. A rule only becomes
executable after validation and compilation succeed, and `diagnostics` are
part of the contract at every stage.

## Documentation

End-user documentation is published on TDspora:

- [Overview](https://tdspora.ai/docs/rulesgen/overview)
- [Quick Start](https://tdspora.ai/docs/rulesgen/getting-started)
- [Repository Docs](https://tdspora.ai/docs/rulesgen/repository-docs)

The source for all public pages, including pages that may not have been
published to TDspora yet, lives in [`docs/public/`](docs/public/):

- [Overview](docs/public/overview.md)
- [Quick Start](docs/public/getting-started.md)
- [Example Workflows](docs/public/workflows.md)
- [API Reference](docs/public/api-reference.md)
- [Python Library](docs/public/python-library.md)
- [Configuration](docs/public/configuration.md)
- [Run Modes](docs/public/run-modes.md)
- [Safety Guardrails](docs/public/safety-guardrails.md)
- [Databricks Models](docs/public/databricks.md)
- [Repository Docs](docs/public/repository-docs.md)

The canonical contributor and agent vocabulary lives in
[`docs/agent-harness/glossary.md`](docs/agent-harness/glossary.md).

Public publishing happens through the `tdm-docs` Docusaurus site, which
imports `docs/public/` during its build. When updating public docs here,
rebuild the `tdm-docs` site with this repository available as the
`RULESGEN_DOCS_SOURCE` input.

## Quick Local Start

The fastest local path is Docker Compose:

<!-- starts local containers and may build images -->
<!-- skip: next -->
```bash
./scripts/run_stack.sh
```

If no LLM provider credential is present, the script falls back to
`RULESGEN_LLM_GATEWAY_BACKEND=stub` so the API can still run locally.

Verify readiness:

<!-- requires a running local rulesgen stack -->
<!-- skip: next -->
```bash
curl -s http://127.0.0.1:8000/health/ready
```

Then follow the local
[Example Workflows](docs/public/workflows.md) documentation.

## What Is Included

- FastAPI HTTP service for health, rules, datasets, jobs, and artifacts.
- Python library API for parsing, compilation, preview, generation, and
  artifact copying.
- Restricted DSL compilation based on Python AST validation.
- Local preview execution for row-phase helpers.
- Subprocess dataset execution for local generation.
- Optional Alibaba OpenSandbox integration for dataset generation.
- Prompt-injection and jailbreak guardrails for natural-language input.
- LLM gateway support for provider-backed and stub translation paths.
- Databricks Foundation Model APIs support through the Databricks extra.
- Filesystem-backed repositories for rules, jobs, prompt audits, uploads, and
  generated artifacts.

## API and Library Entry Points

Use the HTTP API when running the service:

- `GET /health/live`
- `GET /health/ready`
- `POST /rules/parse`
- `POST /rules/compile`
- `POST /rules/preview`
- `POST /rules/execute`
- `POST /datasets/uploads`
- `POST /datasets/generate`
- `POST /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/dataset`
- `GET /jobs/{job_id}/artifacts/{artifact_id}`

Use the Python library when embedding `rulesgen` in another process:

- `parse_rule`
- `compile_rule`
- `preview_rule`
- `execute_generation_plan`
- `download_job_dataset`
- `download_job_artifact`

See [API Reference](docs/public/api-reference.md) and
[Python Library](docs/public/python-library.md) for request shapes and
examples.

## Configuration

Runtime settings use the `RULESGEN_` prefix. In Docker Compose, configuration
comes from `compose.yaml`, `compose.opensandbox.yaml`, and the shell
environment. In host-run mode, configuration comes from `.env` and the shell
environment.

Start with [`.env.example`](.env.example), then review
[Configuration](docs/public/configuration.md) for the full settings guide.

## Development

Install development dependencies:

<!-- synchronizes the local development environment -->
<!-- skip: next -->
```bash
uv sync --extra api --extra dev
```

Useful checks:

<!-- local quality checks -->
<!-- skip: next -->
```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pip-audit
```

Optional extras:

- `api`: FastAPI, Uvicorn, and multipart upload support.
- `dev`: linting, formatting, type checking, tests, audit, and doc-fence
  tooling.
- `guardrails`: ML-backed prompt-injection and jailbreak detection.
- `guardrails-onnx`: ML guardrails with ONNX runtime support.
- `databricks`: Databricks Foundation Model APIs gateway.

Examples:

<!-- synchronizes optional dependency groups -->
<!-- skip: next -->
```bash
uv sync --extra api --extra dev --extra databricks
uv sync --extra api --extra dev --extra guardrails --extra databricks
pip install 'rulesgen[api,dev,databricks]'
pip install 'rulesgen[guardrails-onnx,databricks]'
```

## Design and Contributor Docs

Repository-level design and contributor material remains here:

- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Architecture Overview](requirements/NL-to-Python-Generation-Overview.md)
- [DSL Design](requirements/NL-to-Python-Generation-DSL.md)
- [Uvicorn App Scaffold Notes](https://github.com/tdspora/tdm_rulesgen/blob/main/Recommended%20Scaffold%20for%20a%20Uvicorn-Based%20Python%20REST%20API.md)

## Release Process

Pushes to `main` run CI, build the wheel and sdist, create the GitHub Release
through semantic-release, attach release artifacts, publish distributions to
PyPI, and build and push a Docker image.

Before enabling automated releases, configure these repository secrets:

- `DEPLOY_KEY`
- `PYPI_TOKEN`
- `DOCKER_HUB_USER`
- `DOCKER_HUB_TOKEN`

`pyproject.toml:project.version` and `CHANGELOG.md` are owned by
semantic-release and should not be hand-edited.

## License

This project is licensed under the Apache License 2.0. See
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). This project follows
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Report security issues according
to [`SECURITY.md`](SECURITY.md).
