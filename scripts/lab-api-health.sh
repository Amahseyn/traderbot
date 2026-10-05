#!/usr/bin/env bash
# Shared Lab API health probe (sources only — no set -e).

lab_api_health_url() {
  local lab_port="${LAB_API_PORT:-8765}"
  echo "http://127.0.0.1:${lab_port}/health"
}

# Returns 0 when the API responds with a current feature set.
lab_api_healthy() {
  local health_url="${1:-$(lab_api_health_url)}"
  local timeout_sec="${LAB_HEALTH_TIMEOUT_SEC:-3}"
  local body
  body="$(
    curl -sf --connect-timeout 2 --max-time "${timeout_sec}" "${health_url}" 2>/dev/null || true
  )"
  [[ "${body}" == *'"status":"ok"'* ]] || [[ "${body}" == *'"status": "ok"'* ]] || return 1
  [[ "${body}" == *'market_catalog'* ]] || return 1
  [[ "${body}" == *'live_job_logs'* ]] || return 1
}
