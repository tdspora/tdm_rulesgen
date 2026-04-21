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
#   STATUS_CHECK_CONTEXT        legacy single required Actions check override
#   STATUS_CHECK_CONTEXTS       comma-separated required Actions checks
#                               (default: test)
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
  --description "Python library with an optional FastAPI app for safe rule parsing, compilation, preview execution, and sandbox-backed dataset generation." \
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

echo "==> Ruleset for ${DEFAULT_BRANCH}: $REPO"
RULESET_NAME="${RULESET_NAME:-protect-${DEFAULT_BRANCH}}"

existing_rulesets_json=""
if ! existing_rulesets_json="$(gh api "repos/${REPO}/rulesets?includes_parents=false&per_page=100" --silent 2>/dev/null)"; then
  echo "    (could not list existing rulesets; will attempt create anyway)"
  existing_rulesets_json="[]"
fi
if [ -z "${existing_rulesets_json}" ]; then
  existing_rulesets_json="[]"
fi
ruleset_id="$(
  RULESETS_JSON="$existing_rulesets_json" RULESET_NAME="$RULESET_NAME" python3 - <<'PY'
import json
import os
data = json.loads(os.environ.get("RULESETS_JSON", "[]"))
name = os.environ.get("RULESET_NAME", "")
for rs in data:
    if rs.get("name") == name:
        print(rs.get("id") or "")
        break
PY
)"

python3 - <<'PY' > /tmp/ruleset.json
import json
import os

raw_contexts = os.environ.get("STATUS_CHECK_CONTEXTS", "")
legacy_context = os.environ.get("STATUS_CHECK_CONTEXT", "")

if raw_contexts:
    contexts = [ctx.strip() for ctx in raw_contexts.split(",") if ctx.strip()]
elif legacy_context:
    contexts = [legacy_context.strip()]
else:
    # Prefer the push-scoped check name so PRs don't wait on an event-specific
    # pull_request variant of the same job.
    contexts = ["test"]

integration_id = int(os.environ.get("GITHUB_ACTIONS_APP_ID", "15368"))
approvals = int(os.environ.get("REQUIRED_APPROVAL_COUNT", "0"))
default_branch = os.environ.get("DEFAULT_BRANCH", "main")
ruleset_name = os.environ.get("RULESET_NAME", f"protect-{default_branch}")
include_actions_bypass = os.environ.get("INCLUDE_ACTIONS_BYPASS", "1") not in ("0", "false", "False")

required_status_checks = [{"context": ctx, "integration_id": integration_id} for ctx in contexts]

body = {
    "name": ruleset_name,
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": [f"refs/heads/{default_branch}"], "exclude": []}},
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_linear_history"},
        {
            "type": "pull_request",
            "parameters": {
                "allowed_merge_methods": ["squash", "rebase"],
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_approving_review_count": approvals,
                "required_review_thread_resolution": True,
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "do_not_enforce_on_create": False,
                "required_status_checks": required_status_checks,
                "strict_required_status_checks_policy": True,
            },
        },
    ],
}

if include_actions_bypass:
    # Allow GitHub Actions to bypass PR requirements for release automation.
    # Note: GitHub may reject this for some repos/orgs; the script will retry without it.
    body["bypass_actors"] = [
        {"actor_id": integration_id, "actor_type": "Integration", "bypass_mode": "always"},
    ]

print(json.dumps(body))
PY

apply_ruleset() {
  local method="$1"
  local endpoint="$2"
  local output
  if output="$(gh api "${endpoint}" -X "${method}" --input /tmp/ruleset.json 2>&1)"; then
    return 0
  fi

  if echo "${output}" | grep -q "Actor GitHub Actions integration must be part of the ruleset source or owner organization"; then
    echo "    (Actions bypass rejected by GitHub API; retrying without bypass_actors)"
    INCLUDE_ACTIONS_BYPASS=0 python3 - <<'PY' > /tmp/ruleset.json
import json
import os

raw_contexts = os.environ.get("STATUS_CHECK_CONTEXTS", "")
legacy_context = os.environ.get("STATUS_CHECK_CONTEXT", "")

if raw_contexts:
    contexts = [ctx.strip() for ctx in raw_contexts.split(",") if ctx.strip()]
elif legacy_context:
    contexts = [legacy_context.strip()]
else:
    contexts = ["test"]

integration_id = int(os.environ.get("GITHUB_ACTIONS_APP_ID", "15368"))
approvals = int(os.environ.get("REQUIRED_APPROVAL_COUNT", "0"))
default_branch = os.environ.get("DEFAULT_BRANCH", "main")
ruleset_name = os.environ.get("RULESET_NAME", f"protect-{default_branch}")

required_status_checks = [{"context": ctx, "integration_id": integration_id} for ctx in contexts]
body = {
    "name": ruleset_name,
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": [f"refs/heads/{default_branch}"], "exclude": []}},
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_linear_history"},
        {
            "type": "pull_request",
            "parameters": {
                "allowed_merge_methods": ["squash", "rebase"],
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_approving_review_count": approvals,
                "required_review_thread_resolution": True,
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "do_not_enforce_on_create": False,
                "required_status_checks": required_status_checks,
                "strict_required_status_checks_policy": True,
            },
        },
    ],
}
print(json.dumps(body))
PY
    gh api "${endpoint}" -X "${method}" --input /tmp/ruleset.json --silent
    return 0
  fi

  echo "${output}" >&2
  return 1
}

if [ -n "${ruleset_id}" ]; then
  echo "    Updating ruleset ${RULESET_NAME} (id=${ruleset_id})"
  apply_ruleset "PUT" "repos/${REPO}/rulesets/${ruleset_id}"
else
  echo "    Creating ruleset ${RULESET_NAME}"
  apply_ruleset "POST" "repos/${REPO}/rulesets"
fi

echo
echo "Repository ${REPO} updated."
echo
echo "Important — automated pushes to ${DEFAULT_BRANCH} (e.g. semantic-release + wheel release):"
echo "  The ruleset above requires pull requests. This script attempts to configure a bypass so the GitHub"
echo "  Actions integration can push release commits/tags. If GitHub rejects that via API, add it in the UI:"
echo "  Settings → Rules → Rulesets → ${RULESET_NAME} → Bypass list."
echo
echo "Also before the first release: create a baseline tag matching project.version in pyproject.toml,"
echo "  e.g. git tag v0.1.0 && git push origin v0.1.0."
echo
echo "Optional hardening (UI): Settings → General → Features → Discussions; Moderation options;"
echo "  Security overview and Dependabot version updates are already aligned with public-repo practice."
