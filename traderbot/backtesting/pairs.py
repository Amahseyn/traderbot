"""Two-symbol pair trading on a rolling log-price spread (Traderbot original implementation).

spread_t = log(A_t) − β_t · log(B_t), with β_t from an OLS fit over the previous
``pair_lookback_bars`` bars (bars before t only); z_t = (spread_t − mean) / std of that window.

Modes:
* ``spot_switch`` (default, Nobitex spot has no shorting): when z ≤ −entry hold A (A is cheap
  relative to B); when z ≥ +entry hold B; go to cash when |z| ≤ exit or |z| ≥ stop.
* ``market_neutral``: long the cheap leg and short the rich leg at 50/50 notional. Requires
  margin/futures; simulated only (no borrow costs, funding or liquidation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from traderbot.backtesting.rotation import _aligned_closes

PAIR_MODES = ("spot_switch", "market_neutral")


@dataclass
class PairsResult:
    initial_cash: float
    final_equity: float
    mode: str
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    total_fees: float = 0.0
    total_slippage_cost: float = 0.0
    marked_equity: float = 0.0
    liquidated_equity: float = 0.0
    buy_hold_a_pct: float = 0.0
    buy_hold_b_pct: float = 0.0
    hedge_ratio: float = 1.0

    @property
    def return_pct(self) -> float:
        return (self.final_equity / self.initial_cash - 1.0) * 100.0


def _ols_beta_and_stats(log_a: list[float], log_b: list[float]) -> tuple[float, float, float] | None:
    count = len(log_a)
    mean_a, mean_b = sum(log_a) / count, sum(log_b) / count
    var_b = sum((value - mean_b) ** 2 for value in log_b)
    if var_b <= 0:
        return None
    beta = sum((a - mean_a) * (b - mean_b) for a, b in zip(log_a, log_b)) / var_b
    spreads = [a - beta * b for a, b in zip(log_a, log_b)]
    mean = sum(spreads) / count
    std = math.sqrt(sum((value - mean) ** 2 for value in spreads) / (count - 1))
    if std <= 0:
        return None
    return beta, mean, std


def build_pair_zscores(closes_a: list[float], closes_b: list[float], *, pair_lookback_bars = 72) -> list[float | None]:
    """Causal z-score per bar: the hedge ratio and spread stats use only the prior window."""
    log_a = [math.log(value) for value in closes_a]
    log_b = [math.log(value) for value in closes_b]
    zscores: list[float | None] = []
    for bar_index in range(len(log_a)):
        if bar_index < pair_lookback_bars:
            zscores.append(None)
            continue
        window = slice(bar_index - pair_lookback_bars, bar_index)
        stats = _ols_beta_and_stats(log_a[window], log_b[window])
        if stats is None:
            zscores.append(None)
            continue
        beta, mean, std = stats
        zscores.append((log_a[bar_index] - beta * log_b[bar_index] - mean) / std)
    return zscores


def run_pairs_backtest(
    bars_a: list[dict[str, Any]],
    bars_b: list[dict[str, Any]],
    *,
    pair_lookback_bars = 72,
    pair_entry_z = 2.0,
    pair_exit_z = 0.5,
    pair_stop_z = 4.0,
    mode = "spot_switch",
    initial_cash = 10_000.0,
    fee_rate = 0.0,
    slippage_rate: float = 0.0,
    hedge_ratio: float | None = None,
    liquidate_on_end: bool = True,
) -> PairsResult:
    """Signals use the z-score at bar t's close and fill at bar t+1's close (one bar delay)."""
    if mode not in PAIR_MODES:
        raise ValueError(f"mode must be one of {PAIR_MODES}")
    if not 0 <= pair_exit_z < pair_entry_z < pair_stop_z:
        raise ValueError("need 0 <= pair_exit_z < pair_entry_z < pair_stop_z")
    timestamps, closes = _aligned_closes({"a": bars_a, "b": bars_b})
    closes_a, closes_b = closes["a"], closes["b"]
    if len(timestamps) <= pair_lookback_bars + 1:
        raise ValueError(f"need more than {pair_lookback_bars + 1} shared bars (got {len(timestamps)})")
    zscores = build_pair_zscores(closes_a, closes_b, pair_lookback_bars=pair_lookback_bars)

    cash = initial_cash
    units = {"a": 0.0, "b": 0.0}
    state = 0  # +1 = long A (/short B), −1 = long B (/short A), 0 = flat
    desired = 0
    total_fees = 0.0
    total_slippage_cost = 0.0
    eff_hr = 1.0 if hedge_ratio is None else float(hedge_ratio)
    result = PairsResult(initial_cash=initial_cash, final_equity=initial_cash, mode=mode, hedge_ratio=eff_hr)

    def equity_at(bar_index: int) -> float:
        return cash + units["a"] * closes_a[bar_index] + units["b"] * closes_b[bar_index]

    for bar_index, stamp in enumerate(timestamps):
        prices = {"a": closes_a[bar_index], "b": closes_b[bar_index]}
        if desired != state:
            for leg in ("a", "b"):
                if units[leg] != 0.0:
                    action = "sell" if units[leg] > 0 else "buy"
                    fill = prices[leg] * (1.0 - slippage_rate) if action == "sell" else prices[leg] * (1.0 + slippage_rate)
                    slip_cost = abs(units[leg]) * abs(fill - prices[leg])
                    total_slippage_cost += slip_cost
                    notional = abs(units[leg]) * fill
                    fee = notional * fee_rate
                    cash += units[leg] * fill - fee
                    total_fees += fee
                    units[leg] = 0.0
            if desired != 0:
                long_leg, short_leg = ("a", "b") if desired > 0 else ("b", "a")
                if mode == "spot_switch":
                    fill_long = prices[long_leg] * (1.0 + slippage_rate)
                    total_slippage_cost += (cash / fill_long) * abs(fill_long - prices[long_leg])
                    fee = cash * fee_rate
                    units[long_leg] = (cash - fee) / fill_long
                    cash = 0.0
                    total_fees += fee
                else:
                    weight_long = 1.0 / (1.0 + eff_hr)
                    weight_short = eff_hr / (1.0 + eff_hr)
                    budget_long = cash * weight_long
                    budget_short = cash * weight_short
                    fill_long = prices[long_leg] * (1.0 + slippage_rate)
                    fill_short = prices[short_leg] * (1.0 - slippage_rate)
                    total_slippage_cost += (budget_long / fill_long) * abs(fill_long - prices[long_leg])
                    total_slippage_cost += (budget_short / fill_short) * abs(fill_short - prices[short_leg])
                    fee = (budget_long + budget_short) * fee_rate
                    units[long_leg] = (budget_long - budget_long * fee_rate) / fill_long
                    units[short_leg] = -((budget_short - budget_short * fee_rate) / fill_short)
                    # Short sale proceeds offset long purchase; net cash only decreases by fee
                    cash -= fee
                    total_fees += fee
            result.trades.append({"timestamp": stamp, "position": desired, "equity": round(equity_at(bar_index), 6)})
            state = desired
        result.equity_curve.append((stamp, equity_at(bar_index)))

        zscore = zscores[bar_index]
        if zscore is None:
            continue
        if state == 0:
            if pair_entry_z <= abs(zscore) < pair_stop_z:
                desired = 1 if zscore < 0 else -1
        elif abs(zscore) <= pair_exit_z or abs(zscore) >= pair_stop_z:
            desired = 0

    last_idx = len(timestamps) - 1
    last_stamp = timestamps[-1]
    marked_equity = equity_at(last_idx)
    if liquidate_on_end and state != 0:
        for leg in ("a", "b"):
            if units[leg] != 0.0:
                action = "sell" if units[leg] > 0 else "buy"
                fill = closes[leg][-1] * (1.0 - slippage_rate) if action == "sell" else closes[leg][-1] * (1.0 + slippage_rate)
                slip_cost = abs(units[leg]) * abs(fill - closes[leg][-1])
                total_slippage_cost += slip_cost
                notional = abs(units[leg]) * fill
                fee = notional * fee_rate
                cash += units[leg] * fill - fee
                total_fees += fee
                units[leg] = 0.0
        liquidated_equity = cash
        final_equity = liquidated_equity
        result.equity_curve[-1] = (last_stamp, final_equity)
    else:
        liquidated_equity = marked_equity
        final_equity = marked_equity

    result.final_equity = final_equity
    result.marked_equity = marked_equity
    result.liquidated_equity = liquidated_equity
    result.total_fees = total_fees
    result.total_slippage_cost = total_slippage_cost
    result.buy_hold_a_pct = (closes_a[-1] / closes_a[0] - 1.0) * 100.0
    result.buy_hold_b_pct = (closes_b[-1] / closes_b[0] - 1.0) * 100.0
    return result
