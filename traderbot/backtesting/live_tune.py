from __future__ import annotations

from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import strategy_param_names
from traderbot.backtesting.optimize_select import OptimizeSelectConfig, run_strategy_optimize
from traderbot.backtesting.sweep import (
    DEFAULT_LIVE_TUNE_HOLDOUT_BARS,
    DEFAULT_LIVE_TUNE_MAX_BARS,
    SweepOptions,
)
from traderbot.markets.exchange import DEFAULT_LIVE_EXCHANGE, fetch_live_recent_closed_bars, normalize_live_exchange
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
    "ma_trend": {"trend_fast_period": [10, 20], "trend_slow_period": [50, 100]},
    "rsi_trend": {"rsi_trend_entry": [50, 55, 60], "rsi_trend_exit": [40, 45]},
    "rsi_divergence": {"swing_window_bars": [2, 3], "divergence_rsi_level": [40, 45]},
    "range_breakout": {"lookback_bars": [10, 20], "range_max_width_pct": [0.03, 0.06]},
    "scalp_dip": {"dip_pct": [0.003, 0.005], "take_profit_pct": [0.005, 0.01]},
    "dca": {"dca_interval_bars": [4, 8], "dca_order_count": [5, 10]},
    "grid": {"grid_range_pct": [0.02, 0.05], "grid_levels": [4, 8]},
    "momentum_shock": {"shock_return_std": [2.0, 2.5], "shock_hold_bars": [6, 12]},
    "online_logistic": {"ml_horizon_bars": [3, 6], "ml_buy_threshold": [0.52, 0.55]},
}


def default_live_tune_param_grid(strategy_id: str, *, full: bool = False) -> dict[str, list[Any]]:
    from traderbot.backtesting.robust_defaults import tune_grid_for_strategy

    try:
        return tune_grid_for_strategy(strategy_id, full=full)
    except ValueError:
        pass
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


def fetch_live_tune_bars(
    *,
    exchange: str,
    src: str,
    dst: str,
    interval: str,
    max_bars: int,
) -> list[dict[str, Any]]:
    """Closed OHLC from the live exchange (same source as terminal polling)."""
    if max_bars < 1:
        raise ValueError("max_bars must be at least 1")
    live_exchange = normalize_live_exchange(exchange)
    bars = fetch_live_recent_closed_bars(
        exchange=live_exchange,
        src=src,
        dst=dst,
        resolution=str(interval),
        max_bars=max_bars,
    )
    if not bars:
        raise ValueError(
            f"No closed bars from {live_exchange} for {src}/{dst} at resolution {interval}. "
            "Check the market and resolution."
        )
    return bars


def run_live_tune_sweep(
    *,
    strategy_id: str,
    symbol: str,
    interval: str,
    dst: str,
    src: str | None = None,
    exchange: str | None = None,
    max_bars: int = DEFAULT_LIVE_TUNE_MAX_BARS,
    holdout_tail_bars: int | None = DEFAULT_LIVE_TUNE_HOLDOUT_BARS,
    fee: float = DEFAULT_TRADE_FEE_RATE,
    initial_cash: float | None = None,
    full_grid: bool = False,
) -> dict[str, Any]:
    """Small holdout sweep on recent live-market history; records winner per symbol × resolution."""
    bar_src = (src or symbol).strip().lower()
    if bar_src.endswith("usdt"):
        bar_src = bar_src[:-4]
    elif bar_src.endswith("irt"):
        bar_src = bar_src[:-3]
    live_exchange = normalize_live_exchange(exchange or DEFAULT_LIVE_EXCHANGE)
    bars = fetch_live_tune_bars(
        exchange=live_exchange,
        src=bar_src,
        dst=dst,
        interval=interval,
        max_bars=max_bars,
    )
    param_grid = default_live_tune_param_grid(strategy_id, full=full_grid)
    cash = float(initial_cash) if initial_cash is not None else default_paper_initial_cash(dst)
    if cash <= 0:
        raise ValueError("initial_cash must be positive")
    if holdout_tail_bars is not None and holdout_tail_bars >= max_bars:
        holdout_tail_bars = max(1, max_bars // 5)
    payload = run_strategy_optimize(
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
        config=OptimizeSelectConfig(selection_mode="validation"),
    )
    if payload.get("bars", 0) < MIN_LIVE_TUNE_BARS:
        raise ValueError(
            f"live tune needs at least {MIN_LIVE_TUNE_BARS} bars after trim (got {payload.get('bars')})"
        )
    payload["csv"] = f"{symbol.upper()}_{interval}.csv"
    payload["live_tune"] = {
        "symbol": symbol.upper(),
        "interval": str(interval),
        "max_bars": max_bars,
        "holdout_tail_bars": holdout_tail_bars,
        "initial_cash": cash,
        "dst": dst.strip().lower(),
        "data_source": f"{live_exchange}_api",
        "exchange": live_exchange,
    }
    try_record("sweep_session", sweep_payload=payload)
    return payload
