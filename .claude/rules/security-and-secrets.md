# Security and Secrets Rules

- Never commit secrets or local credentials.
- Never read `.env`, `.env.*`, `~.env`, `.cursor/mcp.json`, or other private token files unless explicitly authorized.
- Never inline LLM provider keys, `LITELLM_*` keys, OpenSandbox / Alibaba OSS credentials (`OSS_ACCESS_KEY_ID`, `OSS_ACCESS_KEY_SECRET`, `OSS_ENDPOINT`), API auth tokens, semantic cache URIs, GitHub tokens, deploy keys, or Docker credentials.
- Treat all credential configuration values as environment variable names (the codebase reads them via `pydantic-settings` in `rulesgen/core/config.py`).
- The compiler enforces a safe Python subset; do **not** weaken the AST validator (`rulesgen/compiler/validator.py`) or the runtime spec sanitization without explicit security review.
- The execution layer is the trust boundary for arbitrary generated code:
  - `local` execution must remain restricted to the validated `RuntimeSpec` surface.
  - OpenSandbox / Alibaba OpenSandbox runners (`rulesgen/execution/opensandbox*.py`, `alibaba_opensandbox.py`) provide isolation — do not bypass them in production paths.
- LLM egress is only permitted to customer-approved gateway endpoints. Never hardcode endpoints in source, prompt templates, sample DSL, or tests.
- The semantic cache (`rulesgen/infra/semantic_cache.py`) must not persist raw prompts or completions that contain customer data; verify key derivation hashes any sensitive input.
- Keep generated artifacts (`.rulesgen-data/`, `~.rulesgen-data/`), built wheels (`dist/`), docs builds (`site/`), and Docker volumes out of source control.
- Logs must be data-free at all levels including debug — no dataset rows, generated samples, prompts, completions, or user identifiers. Validate this claim when touching logging code or middleware.
- Auth backends (`rulesgen/auth/backends/`) are security-critical. Do not add new backends or relax existing ones without explicit approval and tests covering both authenticated and rejected paths.
- CORS, TrustedHost, and middleware configuration in `rulesgen/main.py` is part of the security surface; changes require justification.
- If a change touches the compiler validator, execution runner, LLM gateway, auth, middleware, or generated artifacts, invoke the `rulesgen-security-reviewer` subagent.
