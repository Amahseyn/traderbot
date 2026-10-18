from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from traderbot.algorithms.base import Algorithm, SignalAction
from traderbot.utils.bars import bars_from_ohlc_rows, load_bars_csv, normalize_bar
from traderbot.utils.trading_costs import DEFAULT_BACKTEST_EXECUTION

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
    reason: str = "market"
    liquidity: str = "taker"


@dataclass
class BacktestResult:
    initial_cash: float
    final_equity: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    fee_rate: float = 0.0
    slippage_rate: float = 0.0
    execution: str = DEFAULT_BACKTEST_EXECUTION
    total_fees: float = 0.0
    maker_fee_rate: float = 0.0

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0


def _fill_price(raw_price: float, action: SignalAction, slippage_rate: float) -> float:
    from traderbot.backtesting.broker import fill_price_with_slippage

    return fill_price_with_slippage(raw_price, action, slippage_rate)


def run_backtest(
    algorithm: Algorithm,
    bars: list[dict[str, Any]],
    *,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate = 0.0,
    slippage_rate = 0.0,
    execution: str = DEFAULT_BACKTEST_EXECUTION,
    reset_algorithm: bool = True,
    maker_fee_rate: float | None = None,
    allow_short: bool | None = None,
) -> BacktestResult:
    """
    Backtest with mark-to-market each bar. Default: long-only, full cash on buy, full exit
    on sell; algorithms that return an :class:`OrderSize` from ``order_size()`` get partial fills.

    ``execution="close"`` fills market orders at the signal bar close (optimistic).
    ``execution="next_open"`` fills them at the next bar open, so the fill price is never
    known when the signal fires; a signal on the last bar expires unfilled. Market fills pay
    ``fee_rate`` (taker) plus ``slippage_rate``.

    Algorithms may also return an :class:`~traderbot.algorithms.base.OrderSpec` (limit
    entries, take-profit/stop brackets) or resting quotes; those fill per
    :mod:`traderbot.backtesting.fills`: limits only when a later bar trades through the price,
    at the limit price, paying ``maker_fee_rate`` (default: the venue maker fee paired with
    ``fee_rate``); stops pay the taker fee plus slippage. ``allow_short`` (default: the
    algorithm's ``allow_short``) lets positions go negative; Nobitex (``*IRT``) markets stay
    long-only. The same :class:`~traderbot.backtesting.broker.SimBroker` drives paper trading.
    """
    from traderbot.backtesting.broker import SimBroker

    if not bars:
        raise ValueError("run_backtest requires at least one bar")
    if reset_algorithm:
        algorithm.reset()
    normalized = [normalize_bar(raw_bar) for raw_bar in bars]
    broker = SimBroker(
        algorithm,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        execution=execution,
        maker_fee_rate=maker_fee_rate,
        allow_short=allow_short,
        symbol=next((str(bar.get("symbol")) for bar in normalized[:1] if bar.get("symbol")), None),
    )
    equity_curve: list[tuple[int, float]] = []
    for bar in normalized:
        broker.step(bar)
        equity_curve.append((int(bar["timestamp"]), broker.equity(float(bar["close"]))))

    final_price = float(normalized[-1]["close"])
    final_equity = broker.equity(final_price)
    logger.info(
        "run strategy=%s bars=%d trades=%d initial_cash=%.2f final_equity=%.2f fees=%.2f return_pct=%.2f",
        algorithm.name,
        len(normalized),
        len(broker.trades),
        initial_cash,
        final_equity,
        broker.total_fees,
        (final_equity / initial_cash - 1.0) * 100.0 if initial_cash else 0.0,
    )
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=broker.trades,
        equity_curve=equity_curve,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        execution=execution,
        total_fees=broker.total_fees,
        maker_fee_rate=broker.maker_rate,
    )


def build_trade_log_entries(result: BacktestResult) -> list[dict[str, Any]]:
    """One dict per fill: money in on buys, money out on sells, cash/position after."""
    return [asdict(trade) for trade in result.trades]


def build_cash_flow_summary(result: BacktestResult) -> dict[str, Any]:
    """Run-level money summary: cash in/out per side, fees, PnL."""
    cash_in = sum(trade.cash_before - trade.cash_after for trade in result.trades if trade.action == "buy")
    cash_out = sum(trade.cash_after - trade.cash_before for trade in result.trades if trade.action == "sell")
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
