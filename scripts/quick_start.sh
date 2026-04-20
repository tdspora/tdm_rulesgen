#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
BASE_URL="${BASE_URL:-http://${HOST}:${PORT}}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-30}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-10}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-1}"
SKIP_UV_SYNC="${SKIP_UV_SYNC:-0}"
KEEP_TEMP="${KEEP_TEMP:-0}"

TMP_DIR=$(mktemp -d)
SERVER_LOG="$TMP_DIR/uvicorn.log"
SERVER_PID=""

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

cleanup() {
  local exit_code=$?

  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi

  if [[ "$KEEP_TEMP" == "1" ]]; then
    printf '\nTemp files kept at %s\n' "$TMP_DIR"
    if [[ -n "$SERVER_PID" ]]; then
      printf 'Server log: %s\n' "$SERVER_LOG"
    fi
  else
    rm -rf "$TMP_DIR"
  fi

  exit "$exit_code"
}
trap cleanup EXIT

json_get() {
  local file_path=$1
  local path=$2

  python3 - "$file_path" "$path" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data
for part in sys.argv[2].split("."):
    if isinstance(value, list):
        value = value[int(part)]
    else:
        value = value[part]
if isinstance(value, (dict, list)):
    print(json.dumps(value))
elif value is None:
    print("")
else:
    print(value)
PY
}

print_json() {
  python3 -m json.tool "$1"
}

request_json() {
  local method=$1
  local url=$2
  local output_file=$3
  local body_file=${4:-}
  local http_code

  if [[ -n "$body_file" ]]; then
    http_code=$(curl -sS -o "$output_file" -w "%{http_code}" \
      -X "$method" \
      -H "Content-Type: application/json" \
      --data-binary @"$body_file" \
      "$url")
  else
    http_code=$(curl -sS -o "$output_file" -w "%{http_code}" \
      -X "$method" \
      "$url")
  fi

  if [[ ! "$http_code" =~ ^2 ]]; then
    printf 'Request to %s failed with status %s\n' "$url" "$http_code" >&2
    if [[ -s "$output_file" ]]; then
      print_json "$output_file" >&2 || sed -n '1,160p' "$output_file" >&2
    fi
    return 1
  fi
}

is_service_ready() {
  curl -fsS "$BASE_URL/health/ready" >/dev/null 2>&1
}

wait_for_ready() {
  local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))

  while (( SECONDS < deadline )); do
    if is_service_ready; then
      return 0
    fi

    if [[ -n "$SERVER_PID" ]] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
      printf 'The background service exited before becoming ready.\n' >&2
      [[ -f "$SERVER_LOG" ]] && sed -n '1,200p' "$SERVER_LOG" >&2
      return 1
    fi

    sleep 1
  done

  printf 'Timed out waiting for %s/health/ready\n' "$BASE_URL" >&2
  [[ -f "$SERVER_LOG" ]] && sed -n '1,200p' "$SERVER_LOG" >&2
  return 1
}

start_service_if_needed() {
  if is_service_ready; then
    log "Reusing running service at $BASE_URL"
    return 0
  fi

  if [[ "$SKIP_UV_SYNC" != "1" ]]; then
    log "Installing dependencies with uv sync --extra dev"
    (
      cd "$REPO_ROOT"
      uv sync --extra dev
    )
  fi

  log "Starting rulesgen on $BASE_URL"
  (
    cd "$REPO_ROOT"
    exec uv run uvicorn rulesgen.main:app --host "$HOST" --port "$PORT"
  ) >"$SERVER_LOG" 2>&1 &
  SERVER_PID=$!

  wait_for_ready
}

write_compile_request() {
  local expression=$1
  local output_file=$2

  python3 - "$expression" "$output_file" <<'PY'
import json
import sys
from pathlib import Path

payload = {
    "expression": sys.argv[1],
    "target_column": "bonus",
}
Path(sys.argv[2]).write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
}

main() {
  require_command curl
  require_command python3
  require_command uv

  start_service_if_needed

  local ready_response="$TMP_DIR/ready-response.json"
  local parse_request="$TMP_DIR/parse-request.json"
  local parse_response="$TMP_DIR/parse-response.json"
  local compile_request="$TMP_DIR/compile-request.json"
  local compile_response="$TMP_DIR/compile-response.json"
  local preview_request="$TMP_DIR/preview-request.json"
  local preview_response="$TMP_DIR/preview-response.json"
  local generate_request="$TMP_DIR/generate-request.json"
  local generate_response="$TMP_DIR/generate-response.json"
  local job_response="$TMP_DIR/job-response.json"
  local dsl_candidate
  local artifact_id
  local job_id
  local job_status=""
  local output_path=""

  log "Health check"
  request_json GET "$BASE_URL/health/ready" "$ready_response"
  print_json "$ready_response"

  cat >"$parse_request" <<'JSON'
{
  "source_text": "If job_level is 5 or higher, set bonus to 10 percent of salary.",
  "source_type": "natural_language",
  "target_column": "bonus",
  "schema_columns": ["salary", "job_level", "bonus"]
}
JSON

  log "1. Parse a natural-language rule into a semantic_frame"
  request_json POST "$BASE_URL/rules/parse" "$parse_response" "$parse_request"
  print_json "$parse_response"
  dsl_candidate=$(json_get "$parse_response" "dsl_candidate")

  write_compile_request "$dsl_candidate" "$compile_request"

  log "2. Compile the returned DSL candidate into a compiled_rule"
  request_json POST "$BASE_URL/rules/compile" "$compile_response" "$compile_request"
  print_json "$compile_response"
  artifact_id=$(json_get "$compile_response" "artifact_id")

  cat >"$preview_request" <<JSON
{
  "artifact_id": "$artifact_id",
  "row": {
    "salary": 120000,
    "job_level": 6
  },
  "seed": 99
}
JSON

  log "3. Preview the compiled rule with one sample row"
  request_json POST "$BASE_URL/rules/preview" "$preview_response" "$preview_request"
  print_json "$preview_response"

  cat >"$generate_request" <<'JSON'
{
  "row_count": 3,
  "schema_columns": ["order_id", "line_amount", "order_total"],
  "base_rows": [
    {"order_id": "A", "line_amount": 10},
    {"order_id": "A", "line_amount": 5},
    {"order_id": "B", "line_amount": 7}
  ],
  "rules": [
    {
      "target_column": "order_total",
      "expression": "group_sum(key=col(\"order_id\"), value=col(\"line_amount\"))"
    }
  ],
  "seed": 17
}
JSON

  log "4. Generate a dataset with an aggregate rule"
  request_json POST "$BASE_URL/datasets/generate" "$generate_response" "$generate_request"
  print_json "$generate_response"
  job_id=$(json_get "$generate_response" "job_id")

  log "5. Poll the job and inspect generated artifacts"
  for ((attempt = 1; attempt <= POLL_ATTEMPTS; attempt++)); do
    request_json GET "$BASE_URL/jobs/$job_id" "$job_response"
    job_status=$(json_get "$job_response" "status")
    printf 'Attempt %s/%s: job status = %s\n' "$attempt" "$POLL_ATTEMPTS" "$job_status"
    if [[ "$job_status" != "running" ]]; then
      break
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done

  if [[ "$job_status" == "running" ]]; then
    die "Job $job_id was still running after $POLL_ATTEMPTS attempts."
  fi

  print_json "$job_response"
  output_path=$(json_get "$job_response" "result.output_path")

  if [[ -n "$output_path" && -f "$output_path" ]]; then
    log "Generated dataset at $output_path"
    print_json "$output_path"
  fi
}

main "$@"
