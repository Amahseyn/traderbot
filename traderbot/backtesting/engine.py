from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from traderbot.algorithms.base import Algorithm, SignalAction
from traderbot.utils.bars import bars_from_ohlc_rows, load_bars_csv, normalize_bar

logger = logging.getLogger(__name__)

__all__ = [
    "BacktestResult",
    "EXECUTION_MODES",
    "Trade",
    "bars_from_ohlc_rows",
    "build_cash_flow_summary",
    "build_trade_log_entries",
    "load_bars_csv",
    "normalize_bar",
    "run_backtest",
]

DEFAULT_BACKTEST_INITIAL_CASH = 10_000.0

EXECUTION_MODES = ("close", "next_open")


@dataclass
class Trade:
    timestamp: int
    action: SignalAction
    price: float
    size: float
    fee: float = 0.0
    cash_before: float = 0.0
    cash_after: float = 0.0
    position_after: float = 0.0
    equity_after: float = 0.0


@dataclass
class BacktestResult:
    initial_cash: float
    final_equity: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    fee_rate: float = 0.0
    slippage_rate: float = 0.0
    execution: str = "close"
    total_fees: float = 0.0

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0


def _fill_price(raw_price: float, action: SignalAction, slippage_rate: float) -> float:
    if action == "buy":
        return raw_price * (1.0 + slippage_rate)
    if action == "sell":
        return raw_price * (1.0 - slippage_rate)
    return raw_price


def run_backtest(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate = 0.0,
    slippage_rate = 0.0,
    execution = "close",
) -> BacktestResult:
    """
    Long-only backtest: full cash on buy, full exit on sell, mark-to-market each bar.

    ``execution="close"`` fills at the signal bar close (optimistic intrabar fill).
    ``execution="next_open"`` fills at the next bar open, so the fill price is never
    known when the signal fires; a signal on the last bar expires unfilled.
    """
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if not 0 <= fee_rate < 1:
        raise ValueError("fee_rate must be in [0, 1)")
    if not 0 <= slippage_rate < 1:
        raise ValueError("slippage_rate must be in [0, 1)")
    if execution not in EXECUTION_MODES:
        raise ValueError(f"execution must be one of {EXECUTION_MODES}")
    if not bars:
        raise ValueError("run_backtest requires at least one bar")

    algorithm.reset()
    cash = initial_cash
    position = 0.0
    total_fees = 0.0
    trades: list[Trade] = []
    equity_curve: list[tuple[int, float]] = []
    normalized = [normalize_bar(raw_bar) for raw_bar in bars]

    pending: SignalAction | None = None
    for bar_index, bar in enumerate(normalized):
        bar_open_unix_seconds = int(bar["timestamp"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        signal = algorithm.on_bar(bar)

        action: SignalAction = "hold"
        fill_price = 0.0
        if execution == "close":
            action = signal
            fill_price = _fill_price(close_price, signal, slippage_rate)
        else:
            if pending is not None:
                action = pending
                fill_price = _fill_price(open_price, pending, slippage_rate)
            pending = signal

        if action == "buy" and position == 0 and cash > 0 and fill_price > 0:
            cash_before = cash
            fee = cash_before * fee_rate
            total_fees += fee
            position = (cash_before - fee) / fill_price
            cash = 0.0
            equity_after_trade = position * close_price
            trades.append(
                Trade(
                    timestamp=bar_open_unix_seconds,
                    action="buy",
                    price=fill_price,
                    size=position,
                    fee=fee,
                    cash_before=cash_before,
                    cash_after=cash,
                    position_after=position,
                    equity_after=equity_after_trade,
                )
            )
            logger.info(
                "buy strategy=%s bar=%s price=%.6f size=%.6f cash_in=%.2f fee=%.2f cash_after=%.2f",
                algorithm.name,
                bar_open_unix_seconds,
                fill_price,
                position,
                cash_before,
                fee,
                cash,
            )
        elif action == "sell" and position > 0 and fill_price > 0:
            cash_before = cash
            position_before = position
            proceeds = position_before * fill_price
            fee = proceeds * fee_rate
            total_fees += fee
            cash = proceeds - fee
            trades.append(
                Trade(
                    timestamp=bar_open_unix_seconds,
                    action="sell",
                    price=fill_price,
                    size=position_before,
                    fee=fee,
                    cash_before=cash_before,
                    cash_after=cash,
                    position_after=0.0,
                    equity_after=cash,
                )
            )
            logger.info(
                "sell strategy=%s bar=%s price=%.6f size=%.6f cash_out=%.2f fee=%.2f cash_after=%.2f",
                algorithm.name,
                bar_open_unix_seconds,
                fill_price,
                position_before,
                cash,
                fee,
                cash,
            )
            position = 0.0

        equity = cash + position * close_price
        equity_curve.append((bar_open_unix_seconds, equity))

    final_price = float(normalized[-1]["close"])
    final_equity = cash + position * final_price
    logger.info(
        "run strategy=%s bars=%d trades=%d initial_cash=%.2f final_equity=%.2f fees=%.2f return_pct=%.2f",
        algorithm.name,
        len(normalized),
        len(trades),
        initial_cash,
        final_equity,
        total_fees,
        (final_equity / initial_cash - 1.0) * 100.0 if initial_cash else 0.0,
    )
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        execution=execution,
        total_fees=total_fees,
    )


def build_trade_log_entries(result: BacktestResult) -> list[dict[str, Any]]:
    """One dict per fill: money in on buys, money out on sells, cash/position after."""
    return [asdict(trade) for trade in result.trades]


def build_cash_flow_summary(result: BacktestResult) -> dict[str, Any]:
    """Run-level money summary: cash in/out per side, fees, PnL."""
    cash_in = sum(trade.cash_before for trade in result.trades if trade.action == "buy")
    cash_out = sum(trade.cash_after for trade in result.trades if trade.action == "sell")
    return {
        "initial_cash": result.initial_cash,
        "final_equity": round(result.final_equity, 6),
        "cash_in": round(cash_in, 6),
        "cash_out": round(cash_out, 6),
        "total_fees": round(result.total_fees, 6),
        "net_pnl": round(result.final_equity - result.initial_cash, 6),
        "return_pct": round(result.return_pct, 6),
        "trades": len(result.trades),
        "buys": sum(1 for trade in result.trades if trade.action == "buy"),
        "sells": sum(1 for trade in result.trades if trade.action == "sell"),
    }
