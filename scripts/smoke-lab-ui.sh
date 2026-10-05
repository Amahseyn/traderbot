#!/usr/bin/env bash
# Smoke-test Lab UI routes and proxied API (dev stack must be running).
set -euo pipefail

ui_base="${LAB_UI_BASE:-http://127.0.0.1:3000}"
api_base="${LAB_API_BASE:-http://127.0.0.1:8765}"

fail=0

check_http() {
  local label="$1"
  local url="$2"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" "${url}")"
  if [[ "${code}" != "200" ]]; then
    echo "FAIL ${label}: ${url} → HTTP ${code}" >&2
    fail=1
  else
    echo "OK   ${label}: ${code}"
  fi
}

echo "=== Lab API (${api_base}) ==="
check_http "health" "${api_base}/health"
check_http "stats" "${api_base}/api/stats"
check_http "runs" "${api_base}/api/runs"
check_http "pipelines" "${api_base}/api/pipelines"

echo "=== Lab UI pages (${ui_base}) ==="
for path in / /data /runs /configs /experiments /actions; do
  check_http "${path}" "${ui_base}${path}"
done

echo "=== Lab UI API proxy (${ui_base}/lab-api) ==="
check_http "proxy health" "${ui_base}/lab-api/health"
check_http "proxy stats" "${ui_base}/lab-api/api/stats"

if [[ "${fail}" -ne 0 ]]; then
  exit 1
fi
echo "All smoke checks passed."
