from __future__ import annotations

import math
import statistics
from typing import Any

from traderbot.backtesting.engine import BacktestResult, Trade
from traderbot.backtesting.metrics import buy_and_hold_return_pct, max_drawdown_pct
from traderbot.backtesting.pair_engine import PairBacktestResult
from traderbot.backtesting.vectorbt import vectorbt_is_available, vectorbt_metrics_dict


def _period_returns(equity_curve: list[tuple[int, float]]) -> list[float]:
    if len(equity_curve) < 2:
        return []
    returns: list[float] = []
    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1][1]
        current = equity_curve[index][1]
        if previous > 0:
            returns.append(current / previous - 1.0)
    return returns


def sharpe_ratio_from_equity_curve(
    equity_curve: list[tuple[int, float]],
    *,
    bars_per_year: float,
) -> float:
    returns = _period_returns(equity_curve)
    if len(returns) < 2:
        return 0.0
    mean_return = statistics.mean(returns)
    std_return = statistics.pstdev(returns)
    if std_return == 0:
        return 0.0
    return (mean_return / std_return) * math.sqrt(bars_per_year)


def win_rate_round_trips(trades: list[Trade]) -> float:
    """Percent of completed round-trips (buy then sell) with positive PnL."""
    cash_in = 0.0
    size = 0.0
    wins = 0
    trips = 0
    for trade in trades:
        if trade.action == "buy":
            cash_in = trade.cash_before
            size = trade.size
        elif trade.action == "sell" and size > 0:
            pnl = trade.cash_after - cash_in
            trips += 1
            if pnl > 0:
                wins += 1
            size = 0.0
    if trips == 0:
        return 0.0
    return 100.0 * wins / trips


def bars_per_year_for_resolution(resolution: str) -> float:
    mapping = {
        "1": 365 * 24 * 60,
        "5": 365 * 24 * 12,
        "15": 365 * 24 * 4,
        "30": 365 * 24 * 2,
        "60": 365 * 24,
        "240": 365 * 6,
        "D": 365,
    }
    return float(mapping.get(str(resolution), 365 * 24))


def summarize_single_asset_run(
    result: BacktestResult,
    bars: list[dict[str, Any]],
    *,
    resolution: str,
    algorithm: Any | None = None,
) -> dict[str, Any]:
    bench = buy_and_hold_return_pct(
        bars,
        fee_rate=result.fee_rate,
        slippage_rate=result.slippage_rate,
        execution=result.execution,
    )
    metrics: dict[str, Any] = {
        "return_pct": round(result.return_pct, 4),
        "max_drawdown_pct": round(max_drawdown_pct(result.equity_curve), 4),
        "trade_count": len(result.trades),
        "total_fees": round(result.total_fees, 4),
        "buy_and_hold_return_pct": round(bench, 4),
        "excess_vs_buy_hold_pct": round(result.return_pct - bench, 4),
        "win_rate_pct": round(win_rate_round_trips(result.trades), 4),
        "sharpe_ratio": round(
            sharpe_ratio_from_equity_curve(
                result.equity_curve,
                bars_per_year=bars_per_year_for_resolution(resolution),
            ),
            4,
        ),
    }
    if algorithm is not None and vectorbt_is_available():
        try:
            extra = vectorbt_metrics_dict(
                algorithm,
                bars,
                initial_cash=result.initial_cash,
                fee_rate=result.fee_rate,
                slippage_rate=result.slippage_rate,
                execution=result.execution,
            )
            metrics["vectorbt"] = extra
        except Exception:  # noqa: BLE001
            pass
    return metrics


def summarize_pair_run(result: PairBacktestResult, bars: list[dict[str, Any]], *, resolution: str) -> dict[str, Any]:
    bench = buy_and_hold_return_pct(bars, fee_rate=result.fee_rate, slippage_rate=0.0)
    return {
        "return_pct": round(result.return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "trade_count": len(result.trades),
        "total_fees": round(result.total_fees, 4),
        "buy_and_hold_return_pct": round(bench, 4),
        "excess_vs_buy_hold_pct": round(result.return_pct - bench, 4),
        "sharpe_ratio": round(
            sharpe_ratio_from_equity_curve(
                result.equity_curve,
                bars_per_year=bars_per_year_for_resolution(resolution),
            ),
            4,
        ),
    }


def aggregate_sample_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {}
    returns = [row["return_pct"] for row in samples]
    sharpes = [row.get("sharpe_ratio", 0.0) for row in samples]
    drawdowns = [row.get("max_drawdown_pct", 0.0) for row in samples]
    excess = [row.get("excess_vs_buy_hold_pct", 0.0) for row in samples]
    profitable = sum(1 for value in returns if value > 0)
    return {
        "sample_count": len(samples),
        "mean_return_pct": round(statistics.mean(returns), 4),
        "median_return_pct": round(statistics.median(returns), 4),
        "pct_profitable_windows": round(100.0 * profitable / len(returns), 2),
        "mean_sharpe": round(statistics.mean(sharpes), 4),
        "median_sharpe": round(statistics.median(sharpes), 4),
        "mean_max_drawdown_pct": round(statistics.mean(drawdowns), 4),
        "median_excess_vs_buy_hold_pct": round(statistics.median(excess), 4),
    }
