#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${repo_root}"

lab_host="${LAB_API_HOST:-127.0.0.1}"
lab_port="${LAB_API_PORT:-8765}"

# shellcheck source=scripts/kill-listen-port.sh
source "${repo_root}/scripts/kill-listen-port.sh"
# shellcheck source=scripts/lab-dev-env.sh
source "${repo_root}/scripts/lab-dev-env.sh"

prepare_lab_dev_env "${repo_root}"

lab_python() {
  if [[ -x "${repo_root}/.venv/bin/python" ]]; then
    echo "${repo_root}/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  command -v python
}

run_lab() {
  local py
  py="$(lab_python)"
  PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}" \
    "${py}" -m lab "$@"
}

# serve runs DB init/migrations on startup; a separate init duplicated work and delayed /health.

if [[ "${LAB_KILL_API_PORT:-1}" != "0" ]]; then
  kill_listen_port "${lab_port}"
fi

py="$(lab_python)"
exec env PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${py}" -m lab serve --host "${lab_host}" --port "${lab_port}"
