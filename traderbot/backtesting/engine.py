from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traderbot.algorithms.base import Algorithm, SignalAction
from traderbot.utils.bars import bars_from_ohlc_rows, load_bars_csv, normalize_bar

__all__ = [
    "BacktestResult",
    "Trade",
    "bars_from_ohlc_rows",
    "load_bars_csv",
    "normalize_bar",
    "run_backtest",
]

DEFAULT_BACKTEST_INITIAL_CASH = 10_000.0


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
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate = 0.0,
) -> BacktestResult:
    """
    Long-only backtest: full cash on buy, full exit on sell, mark-to-market each bar.
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

    for raw_bar in bars:
        bar = normalize_bar(raw_bar)
        bar_open_unix_seconds = int(bar["timestamp"])
        close_price = float(bar["close"])
        signal = algorithm.on_bar(bar)

        if signal == "buy" and position == 0 and cash > 0:
            fee = cash * fee_rate
            spend = cash - fee
            position = spend / close_price
            cash = 0.0
            trades.append(
                Trade(timestamp=bar_open_unix_seconds, action="buy", price=close_price, size=position)
            )
        elif signal == "sell" and position > 0:
            proceeds = position * close_price
            fee = proceeds * fee_rate
            cash = proceeds - fee
            trades.append(
                Trade(timestamp=bar_open_unix_seconds, action="sell", price=close_price, size=position)
            )
            position = 0.0

        equity = cash + position * close_price
        equity_curve.append((bar_open_unix_seconds, equity))

    final_price = float(normalize_bar(bars[-1])["close"]) if bars else 0.0
    final_equity = cash + position * final_price
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
    )
