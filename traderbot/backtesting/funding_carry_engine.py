from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traderbot.algorithms.strategies.funding_carry import FundingCarryAlgorithm
from traderbot.backtesting.engine import DEFAULT_BACKTEST_INITIAL_CASH
from traderbot.backtesting.metrics import max_drawdown_pct


@dataclass
class FundingBacktestResult:
    initial_cash: float
    final_equity: float
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    funding_curve: list[tuple[int, float]] = field(default_factory=list)
    total_funding_pnl: float = 0.0
    total_fees: float = 0.0
    trade_count: int = 0

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0

    @property
    def max_drawdown_pct(self) -> float:
        return max_drawdown_pct(self.equity_curve)


def run_funding_carry_backtest(
    algorithm: FundingCarryAlgorithm,
    price_bars: list[dict[str, Any]],
    funding_events: list[dict[str, Any]],
    *,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate: float = 0.00045,
    slippage_rate: float = 0.0005,
) -> FundingBacktestResult:
    """
    Hyperliquid-only paper backtest: short perp when funding is elevated; accrue funding cash flows.
    """
    if not price_bars:
        raise ValueError("price_bars required")
    if not funding_events:
        raise ValueError("funding_events required")

    algorithm.reset()
    cash = initial_cash
    position_coins = 0.0
    total_fees = 0.0
    total_funding_pnl = 0.0
    trade_count = 0
    equity_curve: list[tuple[int, float]] = []
    funding_curve: list[tuple[int, float]] = []

    funding_by_time = sorted(funding_events, key=lambda row: row["time_unix_seconds"])
    funding_index = 0
    last_price = float(price_bars[0]["close"])

    def mark_equity(price: float) -> float:
        return cash + position_coins * price

    for bar in price_bars:
        timestamp = int(bar["timestamp"])
        price = float(bar["close"])
        last_price = price

        while funding_index < len(funding_by_time) and funding_by_time[funding_index]["time_unix_seconds"] <= timestamp:
            event = funding_by_time[funding_index]
            funding_index += 1
            rate = float(event["funding_rate"])
            funding_curve.append((event["time_unix_seconds"], rate * 10000.0))
            signal = algorithm.on_funding(rate)
            equity = mark_equity(price)
            if signal == "enter_short" and position_coins == 0:
                notional = equity * algorithm.position_fraction
                fill = price * (1.0 - slippage_rate)
                size = notional / fill
                fee = notional * fee_rate
                total_fees += fee
                cash -= fee
                position_coins = -size
                trade_count += 1
            elif signal == "exit" and position_coins < 0:
                notional = abs(position_coins) * price
                fee = notional * fee_rate
                total_fees += fee
                cash -= fee
                position_coins = 0.0
                trade_count += 1
            if position_coins < 0:
                notional = abs(position_coins) * price
                # Short receives positive funding when rate > 0
                total_funding_pnl += notional * rate
                cash += notional * rate

        equity_curve.append((timestamp, mark_equity(last_price)))

    return FundingBacktestResult(
        initial_cash=initial_cash,
        final_equity=equity_curve[-1][1] if equity_curve else initial_cash,
        equity_curve=equity_curve,
        funding_curve=funding_curve,
        total_funding_pnl=total_funding_pnl,
        total_fees=total_fees,
        trade_count=trade_count,
    )
