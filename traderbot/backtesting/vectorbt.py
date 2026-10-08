from __future__ import annotations

from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.backtesting.engine import normalize_bar
from traderbot.traders.position import order_action_for_long_only

_STAT_MAP: tuple[tuple[str, str], ...] = (
    ("Total Return [%]", "total_return_pct"),
    ("Sharpe Ratio", "sharpe_ratio"),
    ("Max Drawdown [%]", "max_drawdown_pct"),
    ("Win Rate [%]", "win_rate_pct"),
    ("Profit Factor", "profit_factor"),
    ("Total Trades", "total_trades"),
    ("Expectancy", "expectancy"),
    ("Calmar Ratio", "calmar_ratio"),
)


def _json_number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return int(value)
    return round(f, 6)


def infer_bar_freq(bars: list[dict[str, Any]]):
    """Median spacing between bar timestamps (for annualized vectorbt stats)."""
    import pandas as pd

    if len(bars) < 2:
        return None
    deltas = [
        int(normalize_bar(bars[i + 1])["timestamp"]) - int(normalize_bar(bars[i])["timestamp"])
        for i in range(len(bars) - 1)
    ]
    positive = [d for d in deltas if d > 0]
    if not positive:
        return None
    positive.sort()
    median_s = positive[len(positive) // 2]
    if median_s <= 0:
        return None
    return pd.to_timedelta(median_s, unit="s")


def entry_exit_series(algorithm: Algorithm, bars: list[dict[str, Any]]):
    """Boolean entry/exit arrays from the same bar loop as :func:`traderbot.backtesting.run_backtest`."""
    import pandas as pd

    algorithm.reset()
    entries: list[bool] = []
    exits: list[bool] = []
    closes: list[float] = []
    in_position = False
    for raw in bars:
        bar = normalize_bar(raw)
        signal = algorithm.on_bar(bar)
        order_action = order_action_for_long_only(in_position, signal)
        entries.append(order_action == "buy")
        exits.append(order_action == "sell")
        if order_action == "buy":
            in_position = True
        elif order_action == "sell":
            in_position = False
        closes.append(float(bar["close"]))
    index = pd.Index([int(normalize_bar(b)["timestamp"]) for b in bars], name="timestamp")
    return (
        pd.Series(entries, index=index, dtype=bool),
        pd.Series(exits, index=index, dtype=bool),
        pd.Series(closes, index=index, dtype=float),
    )


def vectorbt_portfolio(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float,
    fee_rate: float,
    slippage_rate: float = 0.0,
):
    import vectorbt as vbt

    entries, exits, close = entry_exit_series(algorithm, bars)
    freq = infer_bar_freq(bars)
    kwargs: dict[str, Any] = {
        "init_cash": initial_cash,
        "fees": fee_rate,
        "slippage": slippage_rate,
        "size": 1.0,
        "size_type": "percent",
    }
    if freq is not None:
        kwargs["freq"] = freq
    return vbt.Portfolio.from_signals(close, entries, exits, **kwargs)


def vectorbt_metrics_dict(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float,
    fee_rate: float,
    slippage_rate: float = 0.0,
) -> dict[str, Any]:
    """
    Risk and trade analytics via vectorbt (optional dependency).

    Uses the same long-only entry/exit gating as :func:`traderbot.backtesting.run_backtest`
    (fees + slippage; fill timing still differs from ``next_open``).
    """
    pf = vectorbt_portfolio(
        algorithm,
        bars,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )
    stats = pf.stats()
    out: dict[str, Any] = {}
    for src_key, dst_key in _STAT_MAP:
        if src_key not in stats.index:
            continue
        out[dst_key] = _json_number(stats[src_key])
    return out


def vectorbt_extra_for_backtest(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float,
    fee_rate: float,
    slippage_rate: float = 0.0,
) -> dict[str, Any] | None:
    try:
        metrics = vectorbt_metrics_dict(
            algorithm,
            bars,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
        )
    except ImportError:
        return None
    return {"vectorbt": metrics}
