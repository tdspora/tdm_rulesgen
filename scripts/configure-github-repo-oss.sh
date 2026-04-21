#!/usr/bin/env bash
# Apply common open-source repository settings via GitHub CLI.
# Prerequisites: GitHub CLI installed (`gh`), authenticated (`gh auth login`), Python 3.
#
# Usage:
#   ./scripts/configure-github-repo-oss.sh
#   ./scripts/configure-github-repo-oss.sh owner/repo
#
# Environment (optional):
#   DEFAULT_BRANCH              default branch to protect (default: main)
#   STATUS_CHECK_CONTEXT        required Actions check (default: ci / test)
#   GITHUB_ACTIONS_APP_ID       GitHub Actions app id on github.com (default: 15368)
#   REQUIRED_APPROVAL_COUNT     approving reviews before merge (default: 0)

set -euo pipefail

REPO="${1:-tdspora/tdm_rulesgen}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

if ! command -v gh >/dev/null 2>&1; then
  echo "Install GitHub CLI: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Run: gh auth login" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to build branch-protection JSON." >&2
  exit 1
fi

echo "==> Repository metadata and merge policy: $REPO"
gh repo edit "$REPO" \
  --description "FastAPI service for safe rule parsing, compilation, preview execution, and sandbox-backed dataset generation." \
  --enable-issues \
  --enable-wiki=false \
  --enable-projects=false \
  --delete-branch-on-merge \
  --enable-squash-merge \
  --enable-merge-commit=false \
  --enable-rebase-merge \
  --allow-update-branch \
  --enable-auto-merge

gh repo edit "$REPO" \
  --add-topic fastapi \
  --add-topic python \
  --add-topic pydantic \
  --add-topic rules-engine \
  --add-topic synthetic-data \
  --add-topic openapi \
  || true

if gh repo edit "$REPO" --allow-forking 2>/dev/null; then
  :
else
  echo "    (allow-forking skipped: only applies to organization-owned repositories)"
fi

echo "==> Secret scanning (public repos): $REPO"
gh repo edit "$REPO" \
  --enable-secret-scanning \
  --enable-secret-scanning-push-protection

echo "==> Dependency / advisory alerts: $REPO"
gh api -X PUT "repos/${REPO}/vulnerability-alerts" >/dev/null 2>&1 || true
gh api -X PUT "repos/${REPO}/private-vulnerability-reporting" >/dev/null 2>&1 || true

echo "==> Branch protection for ${DEFAULT_BRANCH}: $REPO"
python3 -c "
import json, os
ctx = os.environ.get('STATUS_CHECK_CONTEXT', 'ci / test')
app_id = int(os.environ.get('GITHUB_ACTIONS_APP_ID', '15368'))
approvals = int(os.environ.get('REQUIRED_APPROVAL_COUNT', '0'))
body = {
    'required_status_checks': {
        'strict': True,
        'checks': [{'context': ctx, 'app_id': app_id}],
    },
    'enforce_admins': True,
    'required_pull_request_reviews': {
        'dismiss_stale_reviews': True,
        'require_code_owner_reviews': False,
        'required_approving_review_count': approvals,
    },
    'restrictions': None,
    'required_linear_history': True,
    'allow_force_pushes': False,
    'allow_deletions': False,
    'required_conversation_resolution': True,
    'lock_branch': False,
    'allow_fork_syncing': True,
}
print(json.dumps(body))
" | gh api "repos/${REPO}/branches/${DEFAULT_BRANCH}/protection" -X PUT --input - --silent

echo
echo "Repository ${REPO} updated."
echo
echo "Important — automated pushes to ${DEFAULT_BRANCH} (e.g. semantic-release):"
echo "  Branch protection above requires pull requests. The GitHub Actions app must be allowed to"
echo "  bypass that requirement so release workflows can push version bumps."
echo "  In the GitHub UI: Settings → Branches → Branch protection rules → Edit rule for ${DEFAULT_BRANCH}"
echo "  → enable “Allow specified actors to bypass required pull requests” → add “GitHub Actions”."
echo "  (On some accounts the REST API cannot set this bypass; the UI is authoritative.)"
echo
echo "Optional hardening (UI): Settings → General → Features → Discussions; Moderation options;"
echo "  Security overview and Dependabot version updates are already aligned with public-repo practice."
