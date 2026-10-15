"""Multi-symbol strategies that do not fit the single-symbol ``Algorithm`` interface.

* ``run_rotation_backtest`` — altcoin rotation: hold the top-momentum symbol(s) among several
  local OHLC CSVs, rebalancing every N bars. Uses only closes up to each rebalance bar.
* ``build_cross_exchange_spreads`` — cross-exchange arbitrage scanner. Needs two price series
  of the *same* asset in the *same* quote currency from different venues; it reports
  timestamp-aligned spreads net of fees. It does not simulate execution, transfers or latency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RotationResult:
    initial_cash: float
    final_equity: float
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    holdings_log: list[dict[str, Any]] = field(default_factory=list)
    total_fees: float = 0.0

    @property
    def return_pct(self) -> float:
        return (self.final_equity / self.initial_cash - 1.0) * 100.0


def _aligned_closes(bars_by_symbol: dict[str, list[dict[str, Any]]]) -> tuple[list[int], dict[str, list[float]]]:
    close_maps = {
        symbol: {int(bar["timestamp"]): float(bar["close"]) for bar in bars} for symbol, bars in bars_by_symbol.items()
    }
    shared = sorted(set.intersection(*(set(mapping) for mapping in close_maps.values())))
    return shared, {symbol: [mapping[stamp] for stamp in shared] for symbol, mapping in close_maps.items()}


def run_rotation_backtest(
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    *,
    momentum_bars = 24,
    rebalance_bars = 24,
    top_count = 1,
    initial_cash = 10_000.0,
    fee_rate = 0.0,
    require_positive_momentum = True,
) -> RotationResult:
    """Equal-weight the ``top_count`` symbols with the best ``momentum_bars`` return at each
    rebalance (cash when none is positive and ``require_positive_momentum``). Fills at the
    rebalance bar close; momentum uses closes up to and including that bar."""
    if len(bars_by_symbol) < 2:
        raise ValueError("rotation needs at least two symbols")
    if momentum_bars < 1 or rebalance_bars < 1 or top_count < 1:
        raise ValueError("momentum_bars, rebalance_bars and top_count must be >= 1")
    timestamps, closes = _aligned_closes(bars_by_symbol)
    if len(timestamps) <= momentum_bars:
        raise ValueError(f"need more than {momentum_bars} shared bars (got {len(timestamps)})")

    cash = initial_cash
    units: dict[str, float] = {}
    total_fees = 0.0
    result = RotationResult(initial_cash=initial_cash, final_equity=initial_cash)
    for bar_index, stamp in enumerate(timestamps):
        prices = {symbol: series[bar_index] for symbol, series in closes.items()}
        equity = cash + sum(size * prices[symbol] for symbol, size in units.items())
        if bar_index >= momentum_bars and (bar_index - momentum_bars) % rebalance_bars == 0:
            momentum = {
                symbol: series[bar_index] / series[bar_index - momentum_bars] - 1.0
                for symbol, series in closes.items()
                if series[bar_index - momentum_bars] > 0
            }
            ranked = sorted(momentum, key=momentum.get, reverse=True)
            if require_positive_momentum:
                ranked = [symbol for symbol in ranked if momentum[symbol] > 0]
            chosen = ranked[:top_count]
            if set(chosen) != set(units):
                for symbol, size in units.items():
                    proceeds = size * prices[symbol]
                    fee = proceeds * fee_rate
                    cash += proceeds - fee
                    total_fees += fee
                units = {}
                if chosen:
                    slice_cash = cash / len(chosen)
                    for symbol in chosen:
                        fee = slice_cash * fee_rate
                        units[symbol] = (slice_cash - fee) / prices[symbol]
                        total_fees += fee
                    cash = 0.0
                result.holdings_log.append(
                    {"timestamp": stamp, "holdings": chosen, "momentum": {s: round(m, 6) for s, m in momentum.items()}}
                )
            equity = cash + sum(size * prices[symbol] for symbol, size in units.items())
        result.equity_curve.append((stamp, equity))
    result.final_equity = result.equity_curve[-1][1]
    result.total_fees = total_fees
    return result


def build_cross_exchange_spreads(
    venue_a_bars: list[dict[str, Any]],
    venue_b_bars: list[dict[str, Any]],
    *,
    fee_rate_a = 0.0,
    fee_rate_b = 0.0,
    min_net_spread = 0.0,
) -> list[dict[str, Any]]:
    """Timestamp-aligned close spreads between two venues for the same asset and quote.

    ``net_spread`` = gross relative spread minus both venues' taker fees; rows below
    ``min_net_spread`` are dropped. Closes are not executable quotes — treat as a screen.
    """
    closes_a = {int(bar["timestamp"]): float(bar["close"]) for bar in venue_a_bars}
    closes_b = {int(bar["timestamp"]): float(bar["close"]) for bar in venue_b_bars}
    opportunities: list[dict[str, Any]] = []
    for stamp in sorted(set(closes_a) & set(closes_b)):
        price_a, price_b = closes_a[stamp], closes_b[stamp]
        low, high = min(price_a, price_b), max(price_a, price_b)
        if low <= 0:
            continue
        net_spread = (high - low) / low - fee_rate_a - fee_rate_b
        if net_spread < min_net_spread:
            continue
        opportunities.append(
            {
                "timestamp": stamp,
                "buy_venue": "a" if price_a < price_b else "b",
                "price_a": price_a,
                "price_b": price_b,
                "net_spread": round(net_spread, 8),
            }
        )
    return opportunities
