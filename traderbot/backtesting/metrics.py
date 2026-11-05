from __future__ import annotations

import math
from typing import Any, Sequence
import numpy as np

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.backtesting.engine import run_backtest
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
)


class _BuyAndHoldAlgorithm(Algorithm):
    name = "buy_and_hold"

    def __init__(self) -> None:
        self._entered = False

    def reset(self) -> None:
        self._entered = False

    def on_bar(self, bar: Bar) -> SignalAction:
        if self._entered:
            return "hold"
        self._entered = True
        return "buy"


def split_chronological(
    bars: list[dict[str, Any]],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
    warmup_bars: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split bars into chronological train / validation / test slices.

    When ``warmup_bars > 0``, the validation and test slices are each prepended
    with up to ``warmup_bars`` trailing bars from the end of the preceding slice.
    This gives indicator-based strategies the historical lookback they need to
    produce signals from the first non-warmup bar.  The warmup bars are *not*
    part of the disjoint evaluation windows — callers that measure out-of-sample
    return must skip the leading ``warmup_bars`` of the validation/test slice
    (see ``return_pct_excluding_warmup``).
    """
    if not bars:
        raise ValueError("split_chronological requires at least one bar")
    if train_fraction <= 0 or validation_fraction <= 0:
        raise ValueError("train_fraction and validation_fraction must be positive")
    test_fraction = 1.0 - train_fraction - validation_fraction
    if test_fraction <= 0:
        raise ValueError("train_fraction + validation_fraction must be < 1")
    bar_count = len(bars)
    train_end = max(1, int(bar_count * train_fraction))
    validation_end = max(train_end + 1, int(bar_count * (train_fraction + validation_fraction)))
    if validation_end >= bar_count:
        validation_end = bar_count - 1
    if train_end >= validation_end:
        raise ValueError(
            f"not enough bars ({bar_count}) for fractions "
            f"train={train_fraction}, validation={validation_fraction}"
        )
    train = bars[:train_end]
    validation_core = bars[train_end:validation_end]
    test_core = bars[validation_end:]
    if warmup_bars and warmup_bars > 0:
        val_warm = bars[max(0, train_end - warmup_bars):train_end]
        test_warm = bars[max(train_end, validation_end - warmup_bars):validation_end]
        validation = list(val_warm) + list(validation_core)
        test = list(test_warm) + list(test_core)
    else:
        validation = validation_core
        test = test_core
    return train, validation, test


def return_pct_excluding_warmup(
    equity_curve: list[tuple[int, float]],
    warmup_bars: int,
) -> float:
    """Return % measured from the end of the warmup prefix to the final bar.

    Mirrors the walk-forward ``_oos_segment`` equity-curve return: if a position
    was opened during warmup, its unrealised PnL is embedded in the equity at the
    warmup boundary and flows into the return.  Callers that want to exclude
    warmup-opened trades entirely should filter the trade list by timestamp first.
    """
    if not equity_curve:
        return 0.0
    if warmup_bars <= 0 or len(equity_curve) <= warmup_bars:
        start_equity = float(equity_curve[0][1])
    else:
        start_equity = float(equity_curve[warmup_bars - 1][1])
    end_equity = float(equity_curve[-1][1])
    if start_equity <= 0:
        return 0.0
    return (end_equity / start_equity - 1.0) * 100.0


def max_drawdown_pct(equity_curve: list[tuple[int, float]]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0][1]
    worst_drawdown = 0.0
    for _, equity in equity_curve:
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown = (equity / peak - 1.0) * 100.0
            if drawdown < worst_drawdown:
                worst_drawdown = drawdown
    return worst_drawdown


def buy_and_hold_return_pct(
    bars: list[dict[str, Any]],
    *,
    initial_cash: float = 10_000.0,
    fee_rate: float = DEFAULT_TRADE_FEE_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
    execution: str = DEFAULT_BACKTEST_EXECUTION,
) -> float:
    if len(bars) < 2:
        return 0.0
    result = run_backtest(
        _BuyAndHoldAlgorithm(),
        bars,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        execution=execution,
    )
    return result.return_pct


def calculate_returns_from_equity_curve(equity_curve: list[tuple[int, float]]) -> list[float]:
    if len(equity_curve) < 2:
        return []
    returns: list[float] = []
    for index in range(1, len(equity_curve)):
        prev = equity_curve[index - 1][1]
        curr = equity_curve[index][1]
        if prev > 0:
            returns.append(curr / prev - 1.0)
        else:
            returns.append(0.0)
    return returns


def annualized_sharpe_ratio(
    returns: Sequence[float],
    periods_per_year: float = 8760.0,
    risk_free_rate: float = 0.0,
) -> float | None:
    if len(returns) < 2:
        return None
    arr = np.asarray(returns, dtype=float)
    excess = arr - (risk_free_rate / periods_per_year)
    mean = np.mean(excess)
    std = np.std(excess, ddof=1)
    if std <= 1e-12:
        return None
    return float(mean / std * math.sqrt(periods_per_year))


def annualized_sortino_ratio(
    returns: Sequence[float],
    periods_per_year: float = 8760.0,
    target_return: float = 0.0,
) -> float | None:
    if len(returns) < 2:
        return None
    arr = np.asarray(returns, dtype=float)
    excess = arr - (target_return / periods_per_year)
    mean = np.mean(excess)
    downside = np.minimum(0.0, excess)
    downside_var = np.mean(downside ** 2)
    if downside_var <= 1e-12:
        return float(math.inf) if mean > 0 else 0.0
    downside_std = math.sqrt(downside_var)
    return float(mean / downside_std * math.sqrt(periods_per_year))


def calmar_ratio(annualized_return_pct: float, max_drawdown_pct: float) -> float | None:
    dd = abs(max_drawdown_pct)
    if dd <= 1e-12:
        return None
    return float(annualized_return_pct / dd)


def profit_factor(trade_pnls: Sequence[float]) -> float | None:
    if not trade_pnls:
        return None
    gross_profits = sum(p for p in trade_pnls if p > 0)
    gross_losses = abs(sum(p for p in trade_pnls if p < 0))
    if gross_losses <= 1e-12:
        return float(math.inf) if gross_profits > 0 else 1.0
    return float(gross_profits / gross_losses)


def expectancy(trade_pnls: Sequence[float]) -> float | None:
    if not trade_pnls:
        return None
    return float(sum(trade_pnls) / len(trade_pnls))


def turnover_ratio(trades: Sequence[Any], initial_cash: float) -> float:
    if initial_cash <= 0:
        return 0.0
    total_notional = 0.0
    for trade in trades:
        notional = getattr(trade, "notional", 0.0)
        if not notional:
            price = getattr(trade, "price", 0.0)
            size = getattr(trade, "size", 0.0)
            notional = price * size
        total_notional += notional
    return float(total_notional / initial_cash)


def exposure_time_pct(exposure_curve: Sequence[tuple[int, float]]) -> float:
    if not exposure_curve:
        return 0.0
    active_bars = sum(1 for _, exp in exposure_curve if abs(exp) > 1e-12)
    return float(active_bars / len(exposure_curve) * 100.0)


def pair_buy_and_hold_benchmarks(
    bars_a: list[dict[str, Any]],
    bars_b: list[dict[str, Any]],
    *,
    initial_cash: float = 10_000.0,
) -> dict[str, float]:
    if not bars_a or not bars_b:
        return {"buy_hold_a_pct": 0.0, "buy_hold_b_pct": 0.0, "equal_weight_pct": 0.0}
    ret_a = (float(bars_a[-1]["close"]) / float(bars_a[0]["close"]) - 1.0) * 100.0
    ret_b = (float(bars_b[-1]["close"]) / float(bars_b[0]["close"]) - 1.0) * 100.0
    ret_eq = (ret_a + ret_b) / 2.0
    return {
        "buy_hold_a_pct": round(ret_a, 6),
        "buy_hold_b_pct": round(ret_b, 6),
        "equal_weight_pct": round(ret_eq, 6),
    }

