#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../backend" && pwd)"
PYTHON_BIN=""
STARTED_BACKEND=0
BACKEND_LOG=""

cleanup() {
  if [[ "${STARTED_BACKEND}" -eq 1 ]] && [[ -n "${BACKEND_PID:-}" ]] && kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${BACKEND_LOG}" && -f "${BACKEND_LOG}" ]]; then
    rm -f "${BACKEND_LOG}"
  fi
}

trap cleanup EXIT

log() {
  printf '%s\n' "$*"
}

fail() {
  log "FAIL: $*"
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

json_get() {
  "${PYTHON_BIN}" - "$1" "$2" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
key = sys.argv[2]
value = payload
for part in key.split("."):
    if isinstance(value, dict):
        value = value.get(part)
    else:
        value = None
        break
if value is None:
    print("")
elif isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(value)
PY
}

http_get() {
  local path="$1"
  curl -fsS "${BASE_URL}${path}"
}

http_post() {
  local path="$1"
  local body="$2"
  curl -fsS -X POST "${BASE_URL}${path}" \
    -H 'Content-Type: application/json' \
    -d "${body}"
}

wait_for_status() {
  local deadline=$((SECONDS + 30))
  local body
  while (( SECONDS < deadline )); do
    if body="$(http_get /runtime/status 2>/dev/null)"; then
      printf '%s' "${body}"
      return 0
    fi
    sleep 1
  done
  return 1
}

ensure_backend_running() {
  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    return 0
  fi

  need_cmd "${PYTHON_BIN}"
  BACKEND_LOG="$(mktemp)"
  (
    cd "${BACKEND_DIR}"
    "${PYTHON_BIN}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  ) >"${BACKEND_LOG}" 2>&1 &
  BACKEND_PID=$!
  STARTED_BACKEND=1

  sleep 2
  if ! kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    if grep -Eq "could not bind on any address|Address already in use|address already in use" "${BACKEND_LOG}"; then
      STARTED_BACKEND=0
      return 0
    fi
    fail "backend failed to start; see ${BACKEND_LOG}"
  fi
}

main() {
  need_cmd curl
  if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
  [[ -n "${PYTHON_BIN}" ]] || fail "missing required command: python3"

  if ! "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import fastapi  # noqa: F401
import uvicorn  # noqa: F401
PY
  then
    fail "backend dependencies are not available; activate backend/.venv or install fastapi and uvicorn"
  fi

  ensure_backend_running

  status_body="$(wait_for_status)" || fail "backend did not become ready at ${BASE_URL}/runtime/status"
  status_provider="$(json_get "${status_body}" provider_status)"
  log "runtime/status: ${status_provider}"

  dashboard_body="$(http_get /runtime/dashboard)" || fail "GET /runtime/dashboard failed"
  dashboard_active="$(json_get "${dashboard_body}" active_sessions)"
  log "runtime/dashboard: active_sessions=${dashboard_active}"

  if [[ "${status_provider}" != "ready" ]]; then
    log "PASS: backend is reachable"
    log "SKIP: live provider is not configured (${status_provider})"
    log "Configure the default live provider in the backend, then rerun this smoke."
    return 0
  fi

  smoke_body='{"user_request":"Reply with exactly: Stratum runtime console smoke test passed.","max_iterations":1}'
  smoke_response="$(http_post /agent-loop/smoke "${smoke_body}")" || fail "POST /agent-loop/smoke failed"
  smoke_status="$(json_get "${smoke_response}" status)"
  smoke_session="$(json_get "${smoke_response}" session_id)"
  smoke_error="$(json_get "${smoke_response}" error)"

  runs_body="$(http_get /agent-loop/runs)" || fail "GET /agent-loop/runs failed"
  runs_count="$("${PYTHON_BIN}" - "${runs_body}" <<'PY'
import json
import sys

print(len(json.loads(sys.argv[1])))
PY
)"

  if [[ "${smoke_status}" != "completed" ]]; then
    log "FAIL: smoke run ${smoke_session} finished as ${smoke_status}"
    log "error: ${smoke_error}"
    exit 1
  fi

  log "PASS: backend is ready"
  log "PASS: smoke run completed (${smoke_session})"
  log "agent-loop/runs: ${runs_count}"
}

main "$@"
