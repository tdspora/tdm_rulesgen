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

have_any_llm_credentials() {
  [[ -n "${OPENAI_API_KEY:-}" ]] && return 0
  [[ -n "${ANTHROPIC_API_KEY:-}" ]] && return 0
  [[ -n "${GEMINI_API_KEY:-}" ]] && return 0
  [[ -n "${AZURE_API_KEY:-}" ]] && return 0
  return 1
}

resolve_llm_gateway_backend() {
  if [[ -n "${RULESGEN_LLM_GATEWAY_BACKEND:-}" ]]; then
    printf '%s\n' "$RULESGEN_LLM_GATEWAY_BACKEND"
    return 0
  fi

  if have_any_llm_credentials; then
    printf 'litellm\n'
    return 0
  fi

  printf 'stub\n'
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
  local llm_gateway_backend
  llm_gateway_backend=$(resolve_llm_gateway_backend)
  export RULESGEN_LLM_GATEWAY_BACKEND="$llm_gateway_backend"

  if [[ "$llm_gateway_backend" == "stub" ]]; then
    log "No LLM provider credentials detected; using stub translation backend"
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
  stack_files=()
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

