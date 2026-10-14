from __future__ import annotations

import os

# Hyperliquid-style base taker (~0.045% per side). Override via env or CLI/Lab per run.
_DEFAULT_FEE = 0.00045
_DEFAULT_SLIPPAGE = 0.0005


def _rate_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


DEFAULT_TRADE_FEE_RATE = _rate_from_env("TRADERBOT_DEFAULT_FEE_RATE", _DEFAULT_FEE)
DEFAULT_SLIPPAGE_RATE = _rate_from_env("TRADERBOT_DEFAULT_SLIPPAGE_RATE", _DEFAULT_SLIPPAGE)
DEFAULT_BACKTEST_EXECUTION = "next_open"
