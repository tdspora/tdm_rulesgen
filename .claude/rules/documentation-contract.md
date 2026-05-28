---
paths:
  - "README.md"
  - "CONTRIBUTING.md"
  - "SECURITY.md"
  - "CODE_OF_CONDUCT.md"
  - "requirements/NL-to-Python-Generation-*.md"
  - "Recommended Scaffold for a Uvicorn-Based Python REST API.md"
  - "docs/**"
  - "samples/**/*.md"
---

# Documentation Contract

Documentation is a public, testable artifact. These rules apply to every doc file in the project. `CHANGELOG.md` is excluded — it is owned by `python-semantic-release`.

## Canonical vocabulary

- The single source of truth for project vocabulary is `docs/agent-harness/glossary.md`.
- Use the exact term as defined; do not coin synonyms in docs.
- A new term is added to the glossary in the **same change** that introduces it. Cross-link related terms with `[[term]]`.
- Editing a definition in `docs/agent-harness/glossary.md` requires updating every dependent doc that uses the term in the same change.

## Testable examples

- Every Python code fence is executed via `sybil` (see the `rulesgen-docs-testing` skill). A fence that cannot be made runnable must be preceded by `<!-- skip: next -->` on the previous line (sybil's standard directive). A range of fences can be wrapped with `<!-- skip: start --> ... <!-- skip: end -->`. The reason for skipping goes in a separate HTML comment immediately above the skip directive.
- Every shell fence either documents its expected output beneath it OR is preceded by `<!-- skip: next -->`.
- Every HTTP / JSON request or response example must match a Pydantic schema in `src/rulesgen/schemas/` or a Problem Details body in `src/rulesgen/core/problem_details.py`.
- Every documented Settings field must exist in `src/rulesgen/core/config.py` with the same name.
- Every documented endpoint path must exist under `src/rulesgen/api/v1/`.
- Every documented DSL construct must parse with `src/rulesgen/compiler/parser.py` and pass `src/rulesgen/compiler/validator.py`.
- A rejected DSL example uses ` ```dsl !rejected ` and the expected error class on the next line — the test asserts the rejection.

## Link integrity

- Internal links must resolve to a real file or anchor at change time.
- External links must be HTTPS, point at a stable resource, and avoid session-bound query parameters.
- Never reference `localhost`, developer-specific hostnames, or developer-specific filesystem paths.

## Security hygiene

- Never embed: LLM provider keys, `LITELLM_*` keys, OpenSandbox / Alibaba OSS endpoints or keys, OSS access keys, semantic-cache URIs, GitHub tokens, deploy keys, Docker credentials, API auth tokens, real customer dataset rows, generated samples, prompts, or completions.
- Credential references are **environment variable names only** (for example `LITELLM_API_KEY`, `RULESGEN_API_KEY`, `OSS_ACCESS_KEY_ID`), never values.
- LLM endpoint URLs and OpenSandbox endpoint URLs in docs are illustrative placeholders only — never real production hostnames.

## Forbidden hand-edits

- `CHANGELOG.md` — owned by `python-semantic-release`. The only acceptable edit is merge-conflict resolution.
- `pyproject.toml:project.version` — owned by `python-semantic-release`.
- `.github/workflows/ci.yml` release job — escalation only.

## Commit conventions

- Pure docs change: `docs: <summary>`.
- Doc update bundled with code: use the code commit's type (`feat:` / `fix:` / `refactor:`) and include the doc in the same commit.
- Doc that describes a breaking public change: include `BREAKING CHANGE:` footer or `!` marker so `python-semantic-release` produces the right bump.

## When to invoke the documentation harness

- Authoring or updating any file under the `paths:` above triggers the `rulesgen-docs-authoring` skill.
- Testing any file under the `paths:` above triggers the `rulesgen-docs-testing` skill.
- Reviewing a doc change is the responsibility of the `rulesgen-docs-reviewer` agent before commit.
