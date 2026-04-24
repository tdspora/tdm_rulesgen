# rulesgen

`rulesgen` is a secure rule-processing service for synthetic data workflows.

It accepts rule input as either `natural_language` or DSL, translates
`natural_language` requests into an untrusted `semantic_frame` plus DSL
candidate, validates the DSL into a `compiled_rule`, supports local
`execution_preview`, and can execute full dataset generation as a tracked
`job`.

`diagnostics` are part of the contract at every stage. The service does not
treat LLM output as trusted input, and a rule only becomes executable after
validation and compilation succeed.

## Who this site is for

- Teams authoring rules for synthetic data workflows
- Contributors extending the service, compiler, or execution adapters
- Operators evaluating local preview and full dataset-generation paths

## Core flow

1. Parse rule input into a `semantic_frame` plus diagnostics.
2. Treat `natural_language` output and any DSL candidate as untrusted until
   validation succeeds.
3. Compile validated DSL into a `compiled_rule`.
4. Run an `execution_preview` against a sample row and seed.
5. Execute full dataset generation as a `job` and inspect `diagnostics` and
   generated artifacts.

## Start here

- [Quick Start](getting-started.md)
- [Domain Vocabulary](domain-dictionary.md)
- [Repository Docs](repository-docs.md)

## Scope of this site

This GitHub Pages site is intentionally small. It covers the fastest path to
understanding the project and links out to the longer design and contributor
documents that still live in the repository.
