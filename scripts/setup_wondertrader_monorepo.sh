#!/usr/bin/env bash
# Clone WonderTrader into traderbot/vendor/wondertrader (not a separate git repo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${ROOT}/vendor/wondertrader"
if [[ -d "$TARGET/dist" ]]; then
  echo "WonderTrader already at $TARGET"
  exit 0
fi
mkdir -p "$(dirname "$TARGET")"
git clone --depth 1 https://github.com/wondertrader/wondertrader.git "$TARGET"
rm -rf "$TARGET/.git"
echo "Cloned to $TARGET (vendor copy, no nested repo)."
echo "Apply macos_bt patches from docs/wondertrader.md if needed."
