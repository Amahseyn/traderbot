from __future__ import annotations

from math import log
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.spread import rolling_hedge_ratio, spread_zscore_init, spread_zscore_update
from traderbot.algorithms.cli_args import default_strategy_namespace, merge_strategy_namespace
from traderbot.backtesting import run_backtest
from traderbot.backtesting.pair_bars import attach_hedge_bars_from_namespace
from traderbot.backtesting.report import backtest_summary_dict
from traderbot.data.intrahour import enrich_bars_for_csv
from traderbot.backtesting import load_bars_csv


def run_pair_backtest_preview(
    *,
    primary_csv: Path,
    hedge_csv: Path,
    strategy_namespace: Any | None = None,
    initial_cash: float = 10_000.0,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
) -> dict[str, Any]:
    namespace = merge_strategy_namespace(strategy_namespace)
    namespace.hedge_csv = str(hedge_csv)
    csv_path = primary_csv.resolve()
    bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, namespace)
    bars = attach_hedge_bars_from_namespace(bars, namespace, primary_csv=csv_path)
    if len(bars) < 10:
        raise ValueError("Need at least 10 aligned bars for pair preview")
    kwargs = strategy_kwargs_from_namespace("pair_trading", namespace)
    algorithm = algorithm_for_id("pair_trading", **kwargs)
    result = run_backtest(
        algorithm,
        bars,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )
    series = build_pair_chart_series(bars, namespace)
    summary = backtest_summary_dict(
        algorithm,
        result,
        bars=len(bars),
        extra={"strategy_id": "pair_trading", "primary_csv": str(csv_path), "hedge_csv": str(hedge_csv)},
    )
    equity = [{"timestamp": timestamp, "equity": equity} for timestamp, equity in result.equity_curve]
    trades = [
        {
            "timestamp": trade.timestamp,
            "action": trade.action,
            "price": trade.price,
            "equity_after": trade.equity_after,
        }
        for trade in result.trades
    ]
    return {
        "summary": summary,
        "series": series,
        "equity_curve": equity,
        "trades": trades,
    }


def build_pair_chart_series(bars: list[dict[str, Any]], namespace: Any) -> dict[str, list[float | int | None]]:
    lookback = int(getattr(namespace, "lookback", 60))
    hedge_lookback = int(getattr(namespace, "hedge_lookback", 60))
    use_dynamic = bool(getattr(namespace, "use_dynamic_hedge_ratio", True))
    fixed_ratio = float(getattr(namespace, "fixed_hedge_ratio", 1.0))
    from collections import deque

    zstate = spread_zscore_init(lookback)
    primary_window: deque[float] = deque(maxlen=hedge_lookback)
    hedge_window: deque[float] = deque(maxlen=hedge_lookback)
    timestamps: list[int] = []
    primary_closes: list[float] = []
    hedge_closes: list[float] = []
    z_scores: list[float | None] = []
    for bar in bars:
        primary_close = float(bar["close"])
        hedge_close = float(bar["hedge_close"])
        timestamps.append(int(bar["timestamp"]))
        primary_closes.append(primary_close)
        hedge_closes.append(hedge_close)
        primary_window.append(primary_close)
        hedge_window.append(hedge_close)
        hedge_ratio = fixed_ratio
        if use_dynamic:
            dynamic = rolling_hedge_ratio(primary_window, hedge_window)
            if dynamic is not None:
                hedge_ratio = dynamic
        z_scores.append(spread_zscore_update(zstate, primary_close, hedge_close, hedge_ratio))
    log_spreads = [
        log(primary_closes[index]) - log(hedge_closes[index])
        if primary_closes[index] > 0 and hedge_closes[index] > 0
        else None
        for index in range(len(primary_closes))
    ]
    return {
        "timestamp": timestamps,
        "primary_close": primary_closes,
        "hedge_close": hedge_closes,
        "log_spread": log_spreads,
        "z_score": z_scores,
    }
