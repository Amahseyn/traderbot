#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lab_port="${LAB_API_PORT:-8765}"
ui_port="${LAB_UI_PORT:-3000}"
api_pid=""

cleanup() {
  if [[ -n "${api_pid}" ]]; then
    kill "${api_pid}" 2>/dev/null || true
    wait "${api_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# shellcheck source=scripts/kill-listen-port.sh
source "${repo_root}/scripts/kill-listen-port.sh"
# shellcheck source=scripts/lab-api-health.sh
source "${repo_root}/scripts/lab-api-health.sh"

health_url="$(lab_api_health_url)"

echo "Checking Lab API at ${health_url} …"

if ! lab_api_healthy "${health_url}"; then
  if _port_in_use "${lab_port}"; then
    echo "Port ${lab_port} is in use but Lab API is not responding (or outdated) — restarting API…"
    kill_listen_port "${lab_port}" || true
  fi
  echo "Starting Lab API on ${health_url} …"
  LAB_KILL_API_PORT=0 "${repo_root}/run-lab-api.sh" &
  api_pid=$!
  for _ in $(seq 1 60); do
    if lab_api_healthy "${health_url}"; then
      echo "Lab API ready."
      api_pid=""
      break
    fi
    if ! kill -0 "${api_pid}" 2>/dev/null; then
      echo "Lab API exited before becoming ready. Run ./run-lab-api.sh for errors." >&2
      exit 1
    fi
    sleep 0.25
  done
  if ! lab_api_healthy "${health_url}"; then
    echo "Timed out waiting for Lab API at ${health_url}" >&2
    exit 1
  fi
else
  echo "Lab API already running."
fi

if [[ "${LAB_KILL_UI_PORT:-1}" != "0" ]] && _port_in_use "${ui_port}"; then
  echo "Freeing port ${ui_port} for Lab UI…"
  kill_listen_port "${ui_port}" || true
fi

export LAB_API_PROXY_TARGET="${LAB_API_PROXY_TARGET:-http://127.0.0.1:${lab_port}}"
exec "${repo_root}/run-lab-ui.sh"
