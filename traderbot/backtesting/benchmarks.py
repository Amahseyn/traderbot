"""Benchmarks for accumulation strategies (DCA vs lump sum)."""

from __future__ import annotations

from typing import Any

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.backtesting.engine import run_backtest


class _LumpSumAlgorithm(Algorithm):
    name = "lump_sum"

    def __init__(self) -> None:
        self._bought = False

    def reset(self) -> None:
        self._bought = False

    def on_bar(self, bar: Bar) -> SignalAction:
        if self._bought:
            return "hold"
        self._bought = True
        return "buy"


def build_dca_lump_sum_comparison(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float,
    fee_rate: float,
    slippage_rate: float = 0.0,
    execution: str = "close",
) -> dict[str, Any]:
    """Run ``algorithm`` (DCA) and an all-in buy on the first bar with the same cash and costs."""
    costs = {"initial_cash": initial_cash, "fee_rate": fee_rate, "slippage_rate": slippage_rate, "execution": execution}
    dca_result = run_backtest(algorithm, bars, **costs)
    lump_result = run_backtest(_LumpSumAlgorithm(), bars, **costs)
    invested = sum(trade.cash_before - trade.cash_after for trade in dca_result.trades if trade.action == "buy")
    return {
        "dca_return_pct": round(dca_result.return_pct, 6),
        "lump_sum_return_pct": round(lump_result.return_pct, 6),
        "dca_minus_lump_sum_pct": round(dca_result.return_pct - lump_result.return_pct, 6),
        "dca_orders": sum(1 for trade in dca_result.trades if trade.action == "buy"),
        "dca_cash_invested": round(invested, 6),
        "dca_uninvested_cash": round(initial_cash - invested, 6),
    }
