from __future__ import annotations

import os
import sys
from pathlib import Path

_TRADERBOT_ROOT = Path(__file__).resolve().parents[3]


def traderbot_root() -> Path:
    return _TRADERBOT_ROOT


def wondertrader_root() -> Path:
    env = os.environ.get("WONDERTRADER_ROOT", "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if root.is_dir():
            return root
    for candidate in (
        _TRADERBOT_ROOT / "vendor" / "wondertrader",
        _TRADERBOT_ROOT.parent / "wondertrader",
    ):
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        "WonderTrader tree not found. Run scripts/setup_wondertrader_monorepo.sh "
        "or set WONDERTRADER_ROOT."
    )


def dist_bt_runner() -> Path:
    return wondertrader_root() / "dist" / "WtBtRunner"


def macos_bt_runner() -> Path:
    return (
        wondertrader_root()
        / "macos_bt"
        / "build"
        / "build_x64"
        / "Release"
        / "bin"
        / "WtBtRunner"
        / "WtBtRunner"
    )


def logs_dir() -> Path:
    return traderbot_root() / "logs" / "wondertrader"


def ensure_scripts_importable() -> Path:
    root = wondertrader_root()
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return root
