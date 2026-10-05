#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ui_dir="${repo_root}/apps/lab-ui"
lab_port="${LAB_API_PORT:-8765}"
ui_port="${LAB_UI_PORT:-3000}"
ui_host="${LAB_UI_HOST:-0.0.0.0}"

# shellcheck source=scripts/kill-listen-port.sh
source "${repo_root}/scripts/kill-listen-port.sh"
# shellcheck source=scripts/ensure-lab-api.sh
source "${repo_root}/scripts/ensure-lab-api.sh"

if [[ ! -d "${ui_dir}" ]]; then
  echo "lab-ui not found at ${ui_dir}" >&2
  exit 1
fi

ensure_lab_api "${repo_root}"

cd "${ui_dir}"

if [[ ! -f .env.local ]] && [[ -f .env.example ]]; then
  cp .env.example .env.local
fi

if [[ -f .env.local ]] && grep -qE '^NEXT_PUBLIC_API_BASE=http://(127\.0\.0\.1|localhost):' .env.local; then
  if command -v sed >/dev/null 2>&1; then
    sed -i 's|^NEXT_PUBLIC_API_BASE=.*|NEXT_PUBLIC_API_BASE=/lab-api|' .env.local
    echo "Set NEXT_PUBLIC_API_BASE=/lab-api in .env.local (use Next proxy; works on LAN)."
  fi
fi

export LAB_API_PROXY_TARGET="${LAB_API_PROXY_TARGET:-http://127.0.0.1:${lab_port}}"

if [[ ! -d node_modules ]]; then
  npm install
fi

if [[ "${LAB_KILL_UI_PORT:-1}" != "0" ]]; then
  kill_listen_port "${ui_port}" || {
    echo "Free port ${ui_port} manually or set LAB_UI_PORT to another port." >&2
    exit 1
  }
fi

if [[ "${LAB_KEEP_NEXT:-0}" != "1" ]] && [[ -d .next ]]; then
  echo "Removing stale .next (mixing next build + next dev causes 500s). Set LAB_KEEP_NEXT=1 to skip."
  rm -rf .next
fi

echo "Starting Lab UI (next dev) on http://${ui_host}:${ui_port} …"
exec npm run dev -- -H "${ui_host}" -p "${ui_port}"
