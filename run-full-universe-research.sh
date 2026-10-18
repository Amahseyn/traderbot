#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
TOP="${1:-30}"
INTERVALS="${2:-1,5,15,60}"
TRIALS="${3:-60}"
exec "$PY" scripts/run_research_pipeline.py universe \
  --top-markets "$TOP" \
  --intervals "$INTERVALS" \
  --optimize-n-trials "$TRIALS"
