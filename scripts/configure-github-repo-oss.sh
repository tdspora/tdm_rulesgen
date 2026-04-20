#!/usr/bin/env bash
# Apply common open-source repository settings via GitHub CLI.
# Prerequisites: GitHub CLI installed (`gh`), authenticated (`gh auth login`).
#
# Usage:
#   ./scripts/configure-github-repo-oss.sh
#   ./scripts/configure-github-repo-oss.sh owner/repo

set -euo pipefail

REPO="${1:-tdspora/tdm_rulesgen}"

if ! command -v gh >/dev/null 2>&1; then
  echo "Install GitHub CLI: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Run: gh auth login" >&2
  exit 1
fi

gh repo edit "$REPO" \
  --description "FastAPI service for safe rule parsing, compilation, preview execution, and sandbox-backed dataset generation." \
  --enable-issues \
  --enable-wiki=false \
  --enable-projects=false \
  --delete-branch-on-merge \
  --enable-squash-merge \
  --enable-merge-commit=false \
  --enable-rebase-merge

gh repo edit "$REPO" \
  --add-topic fastapi \
  --add-topic python \
  --add-topic pydantic \
  --add-topic rules-engine \
  --add-topic synthetic-data \
  --add-topic openapi

echo "Repository $REPO updated. Enable private vulnerability reporting in the GitHub UI:"
echo "  Settings → Security → Code security → Private vulnerability reporting"
