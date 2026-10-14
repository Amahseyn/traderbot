from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from traderbot.algorithms.pair_trading.spread import align_bars_by_timestamp, spread_z_score_from_closes
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm, PairSignal
from traderbot.backtesting.engine import DEFAULT_BACKTEST_INITIAL_CASH
from traderbot.backtesting.metrics import max_drawdown_pct
from traderbot.utils.bars import normalize_bar

import numpy as np

PairLegAction = Literal["buy", "sell"]


@dataclass
class PairTrade:
    timestamp: int
    leg: Literal["dominant", "hedge"]
    action: PairLegAction
    price: float
    size: float
    fee: float


@dataclass
class PairBacktestResult:
    initial_cash: float
    final_equity: float
    trades: list[PairTrade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    spread_curve: list[tuple[int, float]] = field(default_factory=list)
    z_score_curve: list[tuple[int, float]] = field(default_factory=list)
    fee_rate: float = 0.0
    total_fees: float = 0.0

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0

    @property
    def max_drawdown_pct(self) -> float:
        return max_drawdown_pct(self.equity_curve)


def _fill_price(raw_price: float, action: PairLegAction, slippage_rate: float) -> float:
    if action == "buy":
        return raw_price * (1.0 + slippage_rate)
    return raw_price * (1.0 - slippage_rate)


def _deploy_balanced_portfolio(
    cash: float,
    close_d: float,
    close_h: float,
    hedge_ratio: float,
    fee_rate: float,
    slippage_rate: float,
    timestamp: int,
) -> tuple[float, float, float, list[PairTrade]]:
    """Split cash into dominant / hedge spot holdings (no shorting)."""
    trades: list[PairTrade] = []
    dominant_weight = 1.0 / (1.0 + hedge_ratio)
    hedge_weight = hedge_ratio / (1.0 + hedge_ratio)
    budget_d = cash * dominant_weight
    budget_h = cash * hedge_weight
    fee_d = budget_d * fee_rate
    fee_h = budget_h * fee_rate
    fill_d = _fill_price(close_d, "buy", slippage_rate)
    fill_h = _fill_price(close_h, "buy", slippage_rate)
    dominant_position = (budget_d - fee_d) / fill_d
    hedge_position = (budget_h - fee_h) / fill_h
    trades.append(PairTrade(timestamp, "dominant", "buy", fill_d, dominant_position, fee_d))
    trades.append(PairTrade(timestamp, "hedge", "buy", fill_h, hedge_position, fee_h))
    return 0.0, dominant_position, hedge_position, trades


def run_pair_backtest(
    algorithm: PairTradingAlgorithm,
    dominant_bars: list[dict[str, Any]],
    hedge_bars: list[dict[str, Any]],
    *,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    hedge_ratio: float = 1.0,
    rebalance_fraction: float = 0.25,
    reset_algorithm: bool = True,
) -> PairBacktestResult:
    """
    Spot pair backtest for Nobitex-style markets: hold both legs, rebalance on z-score signals.

    ``hedge_ratio`` matches Hummingbot ``pos_hedge_ratio`` (quote weight on the hedge leg).
    """
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if hedge_ratio <= 0:
        raise ValueError("hedge_ratio must be positive")
    if not 0 < rebalance_fraction <= 1:
        raise ValueError("rebalance_fraction must be in (0, 1]")

    aligned = [normalize_bar(bar) for bar in align_bars_by_timestamp(dominant_bars, hedge_bars)]
    if not aligned:
        raise ValueError("no aligned bars for pair backtest")

    if reset_algorithm:
        algorithm.reset()

    cash = initial_cash
    dominant_position = 0.0
    hedge_position = 0.0
    deployed = False
    spread_state: Literal["flat", "long_spread", "short_spread"] = "flat"
    total_fees = 0.0
    trades: list[PairTrade] = []
    equity_curve: list[tuple[int, float]] = []
    spread_curve: list[tuple[int, float]] = []
    z_score_curve: list[tuple[int, float]] = []
    dominant_history: list[float] = []
    hedge_history: list[float] = []

    def equity_at(close_d: float, close_h: float) -> float:
        return cash + dominant_position * close_d + hedge_position * close_h

    def sell_leg(
        timestamp: int,
        leg: Literal["dominant", "hedge"],
        price: float,
        fraction: float,
    ) -> float:
        nonlocal cash, dominant_position, hedge_position, total_fees
        if leg == "dominant":
            size = dominant_position * fraction
            if size <= 0:
                return 0.0
            fill = _fill_price(price, "sell", slippage_rate)
            proceeds = size * fill
            fee = proceeds * fee_rate
            total_fees += fee
            cash += proceeds - fee
            dominant_position -= size
            trades.append(PairTrade(timestamp, "dominant", "sell", fill, size, fee))
            return proceeds - fee
        size = hedge_position * fraction
        if size <= 0:
            return 0.0
        fill = _fill_price(price, "sell", slippage_rate)
        proceeds = size * fill
        fee = proceeds * fee_rate
        total_fees += fee
        cash += proceeds - fee
        hedge_position -= size
        trades.append(PairTrade(timestamp, "hedge", "sell", fill, size, fee))
        return proceeds - fee

    def buy_leg(
        timestamp: int,
        leg: Literal["dominant", "hedge"],
        price: float,
        quote_amount: float,
    ) -> None:
        nonlocal cash, dominant_position, hedge_position, total_fees
        if quote_amount <= 0 or cash < quote_amount:
            return
        fill = _fill_price(price, "buy", slippage_rate)
        fee = quote_amount * fee_rate
        total_fees += fee
        size = (quote_amount - fee) / fill
        cash -= quote_amount
        if leg == "dominant":
            dominant_position += size
        else:
            hedge_position += size
        trades.append(PairTrade(timestamp, leg, "buy", fill, size, fee))

    for bar in aligned:
        timestamp = int(bar["timestamp"])
        close_d = float(bar["close"])
        close_h = float(bar["hedge_close"])
        dominant_history.append(close_d)
        hedge_history.append(close_h)

        snapshot = spread_z_score_from_closes(
            np.asarray(dominant_history, dtype=float),
            np.asarray(hedge_history, dtype=float),
            lookback_period=algorithm.lookback_period,
        )
        if snapshot is not None:
            spread_curve.append((timestamp, snapshot.spread_pct))
            z_score_curve.append((timestamp, snapshot.z_score))

        if not deployed and len(dominant_history) >= algorithm.lookback_period:
            cash, dominant_position, hedge_position, deploy_trades = _deploy_balanced_portfolio(
                cash,
                close_d,
                close_h,
                hedge_ratio,
                fee_rate,
                slippage_rate,
                timestamp,
            )
            trades.extend(deploy_trades)
            deployed = True

        signal: PairSignal = algorithm.pair_signal(bar)

        if deployed and signal == "long_spread" and spread_state == "flat":
            quote = sell_leg(timestamp, "hedge", close_h, rebalance_fraction)
            buy_leg(timestamp, "dominant", close_d, quote)
            spread_state = "long_spread"
        elif deployed and signal == "short_spread" and spread_state == "flat":
            quote = sell_leg(timestamp, "dominant", close_d, rebalance_fraction)
            buy_leg(timestamp, "hedge", close_h, quote)
            spread_state = "short_spread"
        elif deployed and signal == "close_spread" and spread_state != "flat":
            spread_state = "flat"

        equity_curve.append((timestamp, equity_at(close_d, close_h)))

    final_equity = equity_curve[-1][1] if equity_curve else initial_cash
    return PairBacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
        spread_curve=spread_curve,
        z_score_curve=z_score_curve,
        fee_rate=fee_rate,
        total_fees=total_fees,
    )
