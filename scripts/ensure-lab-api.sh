#!/usr/bin/env bash
# Start Lab FastAPI if /health is not OK. Sources kill-listen-port.sh from repo root.
set -euo pipefail

ensure_lab_api() {
  local repo_root="${1:?repo root}"
  local lab_port="${LAB_API_PORT:-8765}"
  # shellcheck source=scripts/lab-api-health.sh
  source "${repo_root}/scripts/lab-api-health.sh"
  local health_url
  health_url="$(lab_api_health_url)"

  if lab_api_healthy "${health_url}"; then
    return 0
  fi

  # shellcheck source=scripts/kill-listen-port.sh
  source "${repo_root}/scripts/kill-listen-port.sh"

  if _port_in_use "${lab_port}"; then
    echo "Port ${lab_port} in use but Lab API is not responding (or outdated) — restarting…"
    kill_listen_port "${lab_port}" || true
  fi

  echo "Starting Lab API on ${health_url} …"
  LAB_KILL_API_PORT=0 "${repo_root}/run-lab-api.sh" &
  local api_pid=$!
  for _ in $(seq 1 60); do
    if lab_api_healthy "${health_url}"; then
      echo "Lab API ready."
      return 0
    fi
    if ! kill -0 "${api_pid}" 2>/dev/null; then
      echo "Lab API exited before becoming ready. Run ./run-lab-api.sh for errors." >&2
      return 1
    fi
    sleep 0.25
  done
  echo "Timed out waiting for Lab API at ${health_url}" >&2
  return 1
}
