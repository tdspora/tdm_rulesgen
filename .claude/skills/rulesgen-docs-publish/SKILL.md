---
name: rulesgen-docs-publish
description: Use when adding, renaming, reordering, or linking Rulesgen public docs that flow to the tdm-docs Docusaurus site and tdspora.ai. Covers the import pipeline, sidebar/.order mechanics, the "link locally until published" rule, and the lychee link-check and docs-contract validation battery.
---

# Rulesgen Docs Publish Pipeline

## Why this skill exists

`docs/public/*.md` in this repo is **not** the published site — it is a source that a separate repo (`tdm-docs`) imports, transforms, and deploys to tdspora.ai. That indirection has repeatedly cost time: README links to `https://tdspora.ai/docs/rulesgen/*` that 404 in CI because the page was not yet imported/deployed; sidebar entries in the wrong order or with the wrong label; a page whose title showed as the filename or appeared twice. This skill captures the pipeline so those do not recur.

Use `rulesgen-docs-authoring` for *writing* the doc content; use this skill for the *publish/link/ordering* concerns.

## The pipeline (source → site)

1. **Source** lives here: `docs/public/*.md` (currently `overview.md`, `getting-started.md`, `run-modes.md`, `workflows.md`, `configuration.md`, `python-library.md`, `api-reference.md`, `databricks.md`, `safety-guardrails.md`, `repository-docs.md`).
2. **Importer** lives in the sibling repo `tdm-docs`: `scripts/import-rulesgen-docs.mjs`, run via `npm run import:rulesgen-docs` (also runs automatically inside `npm start` and `npm run build`). It:
   - copies each `docs/public/**/*.{md,mdx}` into `tdm-docs/docs/rulesgen/`,
   - **strips the first H1** from the body and sets the page title (see title rules below),
   - rewrites `../domain-dictionary.md` links to the generated `domain-vocabulary` page and rewrites `github.com/tdspora/tdm_rulesgen/blob/main/` links to the pinned ref,
   - regenerates the sidebar block in `tdm-docs/sidebars.js` between the markers `// rulesgen-docs:start` and `// rulesgen-docs:end`.
3. **Deploy**: the tdm-docs site build publishes to tdspora.ai. A page is only reachable at `https://tdspora.ai/docs/rulesgen/<id>` **after** an import + site deploy that includes it.

## Rules that prevent the recurring failures

### Link locally until the page is live
Do **not** link to `https://tdspora.ai/docs/rulesgen/...` from README or other docs for a page that has not yet been imported and deployed — lychee will 404 it in CI. Until the site is confirmed to serve the page, link to the **local relative path** (`docs/public/<name>.md`). Switch to the tdspora.ai URL only once the page is live.

### Title resolution (avoid duplicate / filename titles)
The importer picks the page title as: front-matter `title:` → first H1 in the body → a Title-Cased fallback derived from the filename. Because the first H1 is then **stripped from the body**, a page with no front-matter `title:` and no H1 shows the *filename* as its title; a page whose H1 differs from an intended label can look "duplicated". **Give every public doc a front-matter `title:`** (or a single, correct H1) so the sidebar label and page title are deterministic.

### Ordering via `.order`
Sidebar order is controlled by an optional `.order` file per directory under `docs/public/`. Each non-comment line names a child (filename with or without extension, or a subdirectory). Rules enforced by the importer:
- an entry that matches no child **throws** (`references a missing item`),
- a duplicate entry **throws** (`contains a duplicate item`),
- children not listed are appended in alphabetical order after the listed ones.
When you add or rename a public doc, update the relevant `.order` in the **same change** so ordering stays intentional.

## Validation battery

Run after any docs change (these are the contract tests CI runs):

```bash
uv run --no-sync pytest tests/contract/test_docs_links.py \
                        tests/contract/test_docs_crossref.py \
                        tests/contract/test_docs_glossary.py \
                        tests/contract/test_docs_fences.py \
                        tests/contract/test_docs_dsl.py -q
```

### lychee link check
CI runs `lycheeverse/lychee-action@v2 --config lychee.toml` (see `.github/workflows/ci.yml`). Key gotcha: lychee's `include`/`exclude` are **URL regexes, not file globs** — do not put file paths in them. To verify locally before pushing (if `lychee` is installed):

```bash
lychee --config lychee.toml './**/*.md'
```

`actionlint` and `lychee` are not always installed locally; if a workflow/link check cannot be run locally, say so in the handoff rather than claiming it passed.

## Cross-repo change checklist

When a docs change needs the site updated too (new page, renamed page, reordered nav):
1. Edit `docs/public/**` here (with front-matter `title:` and `.order` updates).
2. In `tdm-docs`, run `npm run import:rulesgen-docs` and confirm the page appears under `docs/rulesgen/` and in the regenerated `sidebars.js` block with the right label/order.
3. Keep README/other links **local** until the tdm-docs deploy that includes the page is live.

## Do not

- Do not edit the generated files in `tdm-docs/docs/rulesgen/` or the block between the `rulesgen-docs:start`/`rulesgen-docs:end` markers by hand — they are overwritten by the importer.
- Do not point external links at unpublished tdspora.ai pages.
- Do not put file paths in lychee `include`/`exclude` (URL regexes only).

## Handoff

State: which `docs/public` files changed, `.order`/front-matter updates, whether the tdm-docs importer was run and the resulting sidebar entries, which contract tests ran and their results, and whether any link/workflow check could not be validated locally.
