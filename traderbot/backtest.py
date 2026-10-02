from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm, SignalAction

_NUMERIC_BAR_KEYS = ("open", "high", "low", "close", "volume")


def normalize_bar(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce OHLC fields to float; keeps export CSV / :mod:`market_data` shape."""
    out = dict(row)
    if "timestamp" in out:
        out["timestamp"] = int(out["timestamp"])
    for key in _NUMERIC_BAR_KEYS:
        if key in out and out[key] != "":
            out[key] = float(out[key])
    return out


def load_bars_csv(path: Path) -> list[dict[str, Any]]:
    """Load candles written by :func:`traderbot.export_csv.write_csv`."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        rows = [normalize_bar(row) for row in reader]
    rows.sort(key=lambda r: r["timestamp"])
    return rows


@dataclass
class Trade:
    timestamp: int
    action: SignalAction
    price: float
    size: float


@dataclass
class BacktestResult:
    initial_cash: float
    final_equity: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0


def run_backtest(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float = 10_000.0,
    fee_rate: float = 0.0,
) -> BacktestResult:
    """
    Long-only simulation on historical bars (same format as ``fetch_ohlc_range`` / export CSV).

    ``buy`` allocates all cash at the bar close; ``sell`` closes the position.
    """
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if not 0 <= fee_rate < 1:
        raise ValueError("fee_rate must be in [0, 1)")

    algorithm.reset()
    cash = initial_cash
    position = 0.0
    trades: list[Trade] = []
    equity_curve: list[tuple[int, float]] = []

    for raw in bars:
        bar = normalize_bar(raw)
        ts = int(bar["timestamp"])
        price = float(bar["close"])
        signal = algorithm.on_bar(bar)

        if signal == "buy" and position == 0 and cash > 0:
            fee = cash * fee_rate
            spend = cash - fee
            position = spend / price
            cash = 0.0
            trades.append(Trade(timestamp=ts, action="buy", price=price, size=position))
        elif signal == "sell" and position > 0:
            proceeds = position * price
            fee = proceeds * fee_rate
            cash = proceeds - fee
            trades.append(Trade(timestamp=ts, action="sell", price=price, size=position))
            position = 0.0

        equity = cash + position * price
        equity_curve.append((ts, equity))

    final_price = float(normalize_bar(bars[-1])["close"]) if bars else 0.0
    final_equity = cash + position * final_price
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
    )


def bars_from_ohlc_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure bar list matches backtest expectations (sorted, numeric OHLC)."""
    normalized = [normalize_bar(r) for r in rows]
    normalized.sort(key=lambda r: r["timestamp"])
    return normalized
