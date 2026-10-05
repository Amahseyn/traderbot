#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${repo_root}"

lab_host="${LAB_API_HOST:-0.0.0.0}"
lab_port="${LAB_API_PORT:-8765}"

# shellcheck source=scripts/kill-listen-port.sh
source "${repo_root}/scripts/kill-listen-port.sh"

run_lab() {
  if command -v traderbot-lab >/dev/null 2>&1; then
    traderbot-lab "$@"
    return
  fi
  if [[ -x "${repo_root}/.venv/bin/traderbot-lab" ]]; then
    "${repo_root}/.venv/bin/traderbot-lab" "$@"
    return
  fi
  PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}" python3 -m lab "$@"
}

run_lab init

if [[ "${LAB_KILL_API_PORT:-1}" != "0" ]]; then
  kill_listen_port "${lab_port}"
fi

if command -v traderbot-lab >/dev/null 2>&1; then
  exec traderbot-lab serve --host "${lab_host}" --port "${lab_port}"
fi
if [[ -x "${repo_root}/.venv/bin/traderbot-lab" ]]; then
  exec "${repo_root}/.venv/bin/traderbot-lab" serve --host "${lab_host}" --port "${lab_port}"
fi
exec env PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m lab serve --host "${lab_host}" --port "${lab_port}"
