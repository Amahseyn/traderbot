#!/usr/bin/env bash
# Clone WonderTrader next to traderbot for local development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"
TARGET="${PARENT}/wondertrader"
if [[ -d "$TARGET/dist" ]]; then
  echo "WonderTrader already at $TARGET"
  exit 0
fi
git clone --depth 1 https://github.com/wondertrader/wondertrader.git "$TARGET"
echo "Cloned to $TARGET — apply local patches from your fork if needed."
echo "export WONDERTRADER_ROOT=$TARGET"
