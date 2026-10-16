from __future__ import annotations

import os
from pathlib import Path

_TRADERBOT_ROOT = Path(__file__).resolve().parents[3]


def traderbot_root() -> Path:
    return _TRADERBOT_ROOT


def finrl_trading_root() -> Path:
    env = os.environ.get("FINRL_TRADING_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    sibling = _TRADERBOT_ROOT.parent / "FinRL-Trading"
    if sibling.is_dir():
        return sibling.resolve()
    raise FileNotFoundError(
        "FinRL-Trading not found. Set FINRL_TRADING_ROOT or clone next to traderbot."
    )


def ensure_finrl_on_path() -> Path:
    root = finrl_trading_root()
    import sys

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
