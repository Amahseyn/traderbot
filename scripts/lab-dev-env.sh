#!/usr/bin/env bash
# Shared Lab dev env: load repo .env, ensure stable API token, mirror token into Lab UI.
set -euo pipefail

lab_python() {
  local repo_root="${1:?repo root}"
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

prepare_lab_dev_env() {
  local repo_root="${1:?repo root}"
  local py
  py="$(lab_python "${repo_root}")"
  # One Python pass: load .env, persist token if missing, sync UI .env.local, print shell exports.
  eval "$(
    REPO_ROOT="${repo_root}" PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}" \
      "${py}" <<'PY'
import os
import secrets
import shlex
import sys
from pathlib import Path

from auth.envfile import load_env_file, upsert_env_vars

repo = Path(os.environ["REPO_ROOT"])
load_env_file(repo / ".env")
if not os.environ.get("LAB_API_TOKEN", "").strip():
    token = secrets.token_urlsafe(24)
    upsert_env_vars(repo / ".env", {"LAB_API_TOKEN": token})
    os.environ["LAB_API_TOKEN"] = token
    print(
        "Wrote LAB_API_TOKEN to .env (restart Lab API if it was already running).",
        file=sys.stderr,
    )
token = os.environ.get("LAB_API_TOKEN", "").strip()
if token:
    ui_env = repo / "apps" / "lab-ui" / ".env.local"
    upsert_env_vars(ui_env, {"NEXT_PUBLIC_LAB_API_TOKEN": token})
    print(f"export LAB_API_TOKEN={shlex.quote(token)}")
for key in sorted(os.environ):
    if key.startswith("COINBEACON_"):
        print(f"export {key}={shlex.quote(os.environ[key])}")
PY
  )"
  if [[ -n "${LAB_API_TOKEN:-}" ]]; then
    export NEXT_PUBLIC_LAB_API_TOKEN="${NEXT_PUBLIC_LAB_API_TOKEN:-${LAB_API_TOKEN}}"
  fi
}
