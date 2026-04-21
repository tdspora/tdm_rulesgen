#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

STACK="${STACK:-opensandbox}"
DETACH="${DETACH:-0}"

log() {
  printf '\n==> %s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ensure_openai_key() {
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    return 0
  fi

  if [[ -n "${CI:-}" ]]; then
    die "OPENAI_API_KEY is required (refusing to prompt in CI)."
  fi

  printf 'OPENAI_API_KEY is not set.\n'
  printf 'Enter OPENAI_API_KEY (input hidden): '
  # shellcheck disable=SC2162
  IFS= read -rs OPENAI_API_KEY
  printf '\n'
  [[ -n "$OPENAI_API_KEY" ]] || die "OPENAI_API_KEY cannot be empty."
  export OPENAI_API_KEY
}

have_any_llm_credentials() {
  [[ -n "${OPENAI_API_KEY:-}" ]] && return 0
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] && return 0
  [[ -n "${GEMINI_API_KEY:-}" ]] && return 0
  [[ -n "${AZURE_API_KEY:-}" ]] && return 0
  return 1
}

ensure_llm_credentials() {
  if have_any_llm_credentials; then
    return 0
  fi

  # Default prompt is OpenAI because it's the most common LiteLLM setup.
  ensure_openai_key
}

compose() {
  (
    cd "$REPO_ROOT"
    docker compose "$@"
  )
}

compose_stack_files() {
  case "$STACK" in
    opensandbox)
      printf '%s\0' "-f" "compose.yaml" "-f" "compose.opensandbox.yaml"
      ;;
    subprocess)
      printf '%s\0' "-f" "compose.yaml"
      ;;
    *)
      die "Unknown STACK '$STACK' (expected: opensandbox|subprocess)"
      ;;
  esac
}

main() {
  require_command docker
  docker compose version >/dev/null 2>&1 || die "Missing required command: docker compose"

  if [[ "$STACK" == "opensandbox" ]]; then
    ensure_llm_credentials
  fi

  local -a stack_files=()
  while IFS= read -r -d '' part; do
    stack_files+=("$part")
  done < <(compose_stack_files)

  local -a args=("up" "--build")
  if [[ "$DETACH" == "1" ]]; then
    args+=("-d")
  fi

  log "Starting stack: $STACK"
  compose "${stack_files[@]}" "${args[@]}"

  log "Next steps"
  cat <<'EOF'
- rulesgen API: http://127.0.0.1:8000
- OpenAPI docs (when enabled): http://127.0.0.1:8000/docs
- Health check: curl -s http://127.0.0.1:8000/health/ready

To stop:
  STACK=opensandbox ./scripts/run_stack.sh down
EOF
}

if [[ "${1:-}" == "down" ]]; then
  require_command docker
  docker compose version >/dev/null 2>&1 || die "Missing required command: docker compose"
  shift || true

  # default to opensandbox on stop, since that's the recommended path
  local -a stack_files=()
  while IFS= read -r -d '' part; do
    stack_files+=("$part")
  done < <(compose_stack_files)

  (
    cd "$REPO_ROOT"
    docker compose "${stack_files[@]}" down
  )
  exit 0
fi

main "$@"

