from __future__ import annotations

from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import strategy_param_names
from traderbot.backtesting.sweep import (
    DEFAULT_LIVE_TUNE_HOLDOUT_BARS,
    DEFAULT_LIVE_TUNE_MAX_BARS,
    SweepOptions,
    run_strategy_sweep,
)
from traderbot.markets.market_data import fetch_recent_closed_bars
from traderbot.recording import try_record
from traderbot.terminal.paper_portfolio import default_paper_initial_cash
from traderbot.utils.trading_costs import DEFAULT_TRADE_FEE_RATE

MIN_LIVE_TUNE_BARS = 40

_LIVE_TUNE_PARAM_GRIDS: dict[str, dict[str, list[Any]]] = {
    "sma_cross": {"fast": [5, 10, 20], "slow": [20, 50]},
    "ema_cross": {"fast": [8, 12, 20], "slow": [26, 50]},
    "rsi_threshold": {"period": [10, 14, 21], "oversold": [25, 30, 35]},
    "macd_cross": {"fast": [8, 12], "slow": [21, 26]},
    "bollinger_mean_reversion": {"period": [15, 20, 25], "num_std": [1.5, 2.0, 2.5]},
    "chart_patterns": {"swing_window_bars": [2, 3, 5], "min_swing_separation_bars": [3, 5, 8]},
    "breakout_atr": {"lookback_bars": [10, 20, 30], "atr_multiplier": [1.5, 2.0, 2.5]},
}


def default_live_tune_param_grid(strategy_id: str) -> dict[str, list[Any]]:
    grid = _LIVE_TUNE_PARAM_GRIDS.get(strategy_id)
    if grid is not None:
        return {name: list(values) for name, values in grid.items()}
    names = strategy_param_names(strategy_id)
    if len(names) < 2:
        raise ValueError(f"live tune needs at least two sweepable params for {strategy_id}")
    defaults = vars(default_strategy_namespace())
    first, second = names[0], names[1]
    return {
        first: _default_sweep_values(defaults.get(first)),
        second: _default_sweep_values(defaults.get(second)),
    }


def _default_sweep_values(default: Any) -> list[Any]:
    if isinstance(default, bool):
        return [True, False]
    if isinstance(default, int):
        return sorted({max(1, default // 2), default, default * 2})
    if isinstance(default, float):
        return sorted({round(default * 0.8, 4), default, round(default * 1.2, 4)})
    return [default]


def fetch_live_tune_bars(symbol: str, interval: str, max_bars: int) -> list[dict[str, Any]]:
    """Closed OHLC from Nobitex (same source as terminal live polling)."""
    if max_bars < 1:
        raise ValueError("max_bars must be at least 1")
    bars = fetch_recent_closed_bars(
        symbol=symbol.upper(),
        resolution=str(interval),
        max_bars=max_bars,
    )
    if not bars:
        raise ValueError(
            f"No closed bars from Nobitex for {symbol.upper()} at resolution {interval}. "
            "Check the market and resolution."
        )
    return bars


def run_live_tune_sweep(
    *,
    strategy_id: str,
    symbol: str,
    interval: str,
    dst: str,
    max_bars: int = DEFAULT_LIVE_TUNE_MAX_BARS,
    holdout_tail_bars: int | None = DEFAULT_LIVE_TUNE_HOLDOUT_BARS,
    fee: float = DEFAULT_TRADE_FEE_RATE,
    initial_cash: float | None = None,
) -> dict[str, Any]:
    """Small holdout sweep on recent Nobitex history; records winner per symbol × resolution."""
    bars = fetch_live_tune_bars(symbol, interval, max_bars)
    param_grid = default_live_tune_param_grid(strategy_id)
    cash = float(initial_cash) if initial_cash is not None else default_paper_initial_cash(dst)
    if cash <= 0:
        raise ValueError("initial_cash must be positive")
    if holdout_tail_bars is not None and holdout_tail_bars >= max_bars:
        holdout_tail_bars = max(1, max_bars // 5)
    payload = run_strategy_sweep(
        SweepOptions(
            strategy_id=strategy_id,
            param_grid=param_grid,
            bars=bars,
            cash=cash,
            fee=fee,
            holdout_tail_bars=holdout_tail_bars,
            max_bars=max_bars,
            min_trades=0,
            max_combos=64,
        ),
        base_namespace=default_strategy_namespace(),
    )
    if payload.get("bars", 0) < MIN_LIVE_TUNE_BARS:
        raise ValueError(
            f"live tune needs at least {MIN_LIVE_TUNE_BARS} bars after trim (got {payload.get('bars')})"
        )
    payload["live_tune"] = {
        "symbol": symbol.upper(),
        "interval": str(interval),
        "max_bars": max_bars,
        "holdout_tail_bars": holdout_tail_bars,
        "initial_cash": cash,
        "dst": dst.strip().lower(),
        "data_source": "nobitex_api",
    }
    try_record("sweep_session", sweep_payload=payload)
    return payload
