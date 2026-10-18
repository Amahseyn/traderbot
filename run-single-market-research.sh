#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
SYMBOL="${1:-ARBUSDT}"
INTERVALS="${2:-1,5,15,60}"
TRIALS="${3:-80}"
exec "$PY" scripts/run_research_pipeline.py single \
  --symbol "$SYMBOL" \
  --intervals "$INTERVALS" \
  --optimize-n-trials "$TRIALS"
