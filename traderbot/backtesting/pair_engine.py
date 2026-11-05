from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from traderbot.algorithms.pair_trading.sizing import (
    PairSizingModel,
    calculate_pair_position_sizes,
)
from traderbot.algorithms.pair_trading.spread import (
    align_bars_by_timestamp,
    spread_z_score_from_closes,
)
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm, PairSignal
from traderbot.backtesting.engine import DEFAULT_BACKTEST_INITIAL_CASH
from traderbot.backtesting.fills import simulated_fill_price
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
    notional: float = 0.0
    beta_exposure: float = 0.0


@dataclass
class PairBacktestResult:
    initial_cash: float
    final_equity: float
    trades: list[PairTrade] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    spread_curve: list[tuple[int, float]] = field(default_factory=list)
    z_score_curve: list[tuple[int, float]] = field(default_factory=list)
    exposure_curve: list[tuple[int, float]] = field(default_factory=list)
    gross_exposure_curve: list[tuple[int, float]] = field(default_factory=list)
    net_exposure_curve: list[tuple[int, float]] = field(default_factory=list)
    fee_rate: float = 0.0
    total_fees: float = 0.0
    total_slippage_cost: float = 0.0
    total_funding: float = 0.0
    total_funding_paid: float = 0.0
    total_funding_received: float = 0.0
    marked_equity: float = 0.0
    liquidated_equity: float = 0.0
    win_rate_pct: float | None = None
    sizing_model: str = "hedge_ratio"
    spread_model: str = "legacy"
    execution: str = "close"
    breakdown_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0

    @property
    def max_drawdown_pct(self) -> float:
        return max_drawdown_pct(self.equity_curve)


@dataclass
class MultiPairBacktestResult:
    initial_cash: float
    final_equity: float
    pair_results: dict[str, PairBacktestResult]
    portfolio_equity_curve: list[tuple[int, float]]
    portfolio_exposure_curve: list[tuple[int, float]] = field(default_factory=list)
    total_fees: float = 0.0
    total_funding: float = 0.0
    total_slippage_cost: float = 0.0

    @property
    def return_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.final_equity / self.initial_cash - 1.0) * 100.0

    @property
    def max_drawdown_pct(self) -> float:
        return max_drawdown_pct(self.portfolio_equity_curve)


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
    execution: Literal["next_open", "close"] = "close",
    liquidate_on_end: bool = True,
    **kwargs: Any,
) -> PairBacktestResult:
    """
    Spot pair backtest for Nobitex-style markets: hold both legs, rebalance on z-score signals.

    ``hedge_ratio`` matches Hummingbot ``pos_hedge_ratio`` (quote weight on the hedge leg).
    """
    if kwargs.get("mode") == "market_neutral" or kwargs.get("allow_short"):
        raise ValueError(
            "Nobitex spot does not support native short selling; use spot rebalance mode "
            "or run perpetual pair backtest for Hyperliquid instead."
        )
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if hedge_ratio <= 0:
        raise ValueError("hedge_ratio must be positive")
    if not 0 < rebalance_fraction <= 1:
        raise ValueError("rebalance_fraction must be in (0, 1]")

    effective_hedge_ratio = (
        getattr(algorithm, "hedge_ratio", hedge_ratio)
        if hedge_ratio == 1.0 and getattr(algorithm, "hedge_ratio", 1.0) != 1.0
        else hedge_ratio
    )
    effective_intercept = getattr(algorithm, "intercept", 0.0)
    effective_rolling_ols = getattr(algorithm, "rolling_ols", False)

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
    total_slippage_cost = 0.0
    trades: list[PairTrade] = []
    equity_curve: list[tuple[int, float]] = []
    spread_curve: list[tuple[int, float]] = []
    z_score_curve: list[tuple[int, float]] = []
    exposure_curve: list[tuple[int, float]] = []
    gross_exposure_curve: list[tuple[int, float]] = []
    net_exposure_curve: list[tuple[int, float]] = []
    dominant_history: list[float] = []
    hedge_history: list[float] = []
    entry_equity: float | None = None
    round_trips = 0
    winning_trips = 0

    def equity_at(close_d: float, close_h: float) -> float:
        return cash + dominant_position * close_d + hedge_position * close_h

    def sell_leg(
        timestamp: int,
        leg: Literal["dominant", "hedge"],
        price: float,
        fraction: float,
    ) -> float:
        nonlocal cash, dominant_position, hedge_position, total_fees, total_slippage_cost
        if leg == "dominant":
            size = dominant_position * fraction
            if size <= 0:
                return 0.0
            fill = _fill_price(price, "sell", slippage_rate)
            total_slippage_cost += size * abs(fill - price)
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
        total_slippage_cost += size * abs(fill - price)
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
        nonlocal cash, dominant_position, hedge_position, total_fees, total_slippage_cost
        if quote_amount <= 0 or cash < quote_amount:
            return
        fill = _fill_price(price, "buy", slippage_rate)
        fee = quote_amount * fee_rate
        total_fees += fee
        size = (quote_amount - fee) / fill
        total_slippage_cost += size * abs(fill - price)
        cash -= quote_amount
        if leg == "dominant":
            dominant_position += size
        else:
            hedge_position += size
        trades.append(PairTrade(timestamp, leg, "buy", fill, size, fee))

    pending_rebalance: tuple[str, float, float] | None = None

    for bar in aligned:
        timestamp = int(bar["timestamp"])
        open_d = float(bar.get("open", bar["close"]))
        open_h = float(bar.get("hedge_open", bar["hedge_close"]))
        close_d = float(bar["close"])
        close_h = float(bar["hedge_close"])
        dominant_history.append(close_d)
        hedge_history.append(close_h)

        if execution == "next_open" and pending_rebalance is not None:
            reb_action, p_d, p_h = pending_rebalance
            if reb_action == "long_spread":
                entry_equity = equity_at(open_d, open_h)
                quote = sell_leg(timestamp, "hedge", open_h, rebalance_fraction)
                buy_leg(timestamp, "dominant", open_d, quote)
                spread_state = "long_spread"
            elif reb_action == "short_spread":
                entry_equity = equity_at(open_d, open_h)
                quote = sell_leg(timestamp, "dominant", open_d, rebalance_fraction)
                buy_leg(timestamp, "hedge", open_h, quote)
                spread_state = "short_spread"
            elif reb_action == "close_spread":
                tot_eq = equity_at(open_d, open_h)
                dominant_weight = 1.0 / (1.0 + hedge_ratio)
                hedge_weight = hedge_ratio / (1.0 + hedge_ratio)
                val_d = dominant_position * open_d
                val_h = hedge_position * open_h
                target_val_d = tot_eq * dominant_weight
                target_val_h = tot_eq * hedge_weight

                if val_d > target_val_d and val_d > 0:
                    fraction_to_sell = min(1.0, max(0.0, (val_d - target_val_d) / val_d))
                    quote = sell_leg(timestamp, "dominant", open_d, fraction_to_sell)
                    buy_leg(timestamp, "hedge", open_h, quote)
                elif val_h > target_val_h and val_h > 0:
                    fraction_to_sell = min(1.0, max(0.0, (val_h - target_val_h) / val_h))
                    quote = sell_leg(timestamp, "hedge", open_h, fraction_to_sell)
                    buy_leg(timestamp, "dominant", open_d, quote)

                spread_state = "flat"
                if entry_equity is not None:
                    round_trips += 1
                    if equity_at(open_d, open_h) > entry_equity:
                        winning_trips += 1
                    entry_equity = None
            pending_rebalance = None

        snapshot = spread_z_score_from_closes(
            np.asarray(dominant_history, dtype=float),
            np.asarray(hedge_history, dtype=float),
            lookback_period=algorithm.lookback_period,
            model=algorithm.spread_model,
            hedge_ratio=effective_hedge_ratio,
            intercept=effective_intercept,
            rolling_ols=effective_rolling_ols,
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
            if execution == "next_open":
                pending_rebalance = ("long_spread", close_d, close_h)
            else:
                entry_equity = equity_at(close_d, close_h)
                quote = sell_leg(timestamp, "hedge", close_h, rebalance_fraction)
                buy_leg(timestamp, "dominant", close_d, quote)
                spread_state = "long_spread"
        elif deployed and signal == "short_spread" and spread_state == "flat":
            if execution == "next_open":
                pending_rebalance = ("short_spread", close_d, close_h)
            else:
                entry_equity = equity_at(close_d, close_h)
                quote = sell_leg(timestamp, "dominant", close_d, rebalance_fraction)
                buy_leg(timestamp, "hedge", close_h, quote)
                spread_state = "short_spread"
        elif deployed and signal == "close_spread" and spread_state != "flat":
            if execution == "next_open":
                pending_rebalance = ("close_spread", close_d, close_h)
            else:
                tot_eq = equity_at(close_d, close_h)
                dominant_weight = 1.0 / (1.0 + hedge_ratio)
                hedge_weight = hedge_ratio / (1.0 + hedge_ratio)
                val_d = dominant_position * close_d
                val_h = hedge_position * close_h
                target_val_d = tot_eq * dominant_weight
                target_val_h = tot_eq * hedge_weight

                if val_d > target_val_d and val_d > 0:
                    fraction_to_sell = min(1.0, max(0.0, (val_d - target_val_d) / val_d))
                    quote = sell_leg(timestamp, "dominant", close_d, fraction_to_sell)
                    buy_leg(timestamp, "hedge", close_h, quote)
                elif val_h > target_val_h and val_h > 0:
                    fraction_to_sell = min(1.0, max(0.0, (val_h - target_val_h) / val_h))
                    quote = sell_leg(timestamp, "hedge", close_h, fraction_to_sell)
                    buy_leg(timestamp, "dominant", close_d, quote)

                spread_state = "flat"
                if entry_equity is not None:
                    round_trips += 1
                    if equity_at(close_d, close_h) > entry_equity:
                        winning_trips += 1
                    entry_equity = None

        cur_eq = equity_at(close_d, close_h)
        equity_curve.append((timestamp, cur_eq))
        net_exp = dominant_position * close_d + hedge_position * close_h
        exposure_curve.append((timestamp, net_exp))
        net_exposure_curve.append((timestamp, net_exp))
        gross_exposure_curve.append((timestamp, net_exp))

    last_close_d = dominant_history[-1] if dominant_history else 0.0
    last_close_h = hedge_history[-1] if hedge_history else 0.0
    last_timestamp = int(aligned[-1]["timestamp"]) if aligned else 0
    marked_equity = equity_at(last_close_d, last_close_h)

    has_open_positions = (dominant_position > 1e-12 or hedge_position > 1e-12)
    if has_open_positions and liquidate_on_end:
        if dominant_position > 0:
            sell_leg(last_timestamp, "dominant", last_close_d, 1.0)
        if hedge_position > 0:
            sell_leg(last_timestamp, "hedge", last_close_h, 1.0)
        liquidated_equity = cash
        final_equity = liquidated_equity
        if equity_curve:
            equity_curve[-1] = (last_timestamp, final_equity)
            exposure_curve[-1] = (last_timestamp, 0.0)
            net_exposure_curve[-1] = (last_timestamp, 0.0)
            gross_exposure_curve[-1] = (last_timestamp, 0.0)
        else:
            equity_curve.append((last_timestamp, final_equity))
            exposure_curve.append((last_timestamp, 0.0))
            net_exposure_curve.append((last_timestamp, 0.0))
            gross_exposure_curve.append((last_timestamp, 0.0))
    else:
        exit_fee = (dominant_position * last_close_d + hedge_position * last_close_h) * fee_rate
        exit_slippage = (dominant_position * last_close_d + hedge_position * last_close_h) * slippage_rate
        liquidated_equity = marked_equity - exit_fee - exit_slippage
        final_equity = marked_equity

    win_rate_pct = round(winning_trips / round_trips * 100.0, 2) if round_trips > 0 else None
    return PairBacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
        spread_curve=spread_curve,
        z_score_curve=z_score_curve,
        exposure_curve=exposure_curve,
        gross_exposure_curve=gross_exposure_curve,
        net_exposure_curve=net_exposure_curve,
        fee_rate=fee_rate,
        total_fees=total_fees,
        total_slippage_cost=total_slippage_cost,
        marked_equity=marked_equity,
        liquidated_equity=liquidated_equity,
        win_rate_pct=win_rate_pct,
        spread_model=algorithm.spread_model,
        execution=execution,
    )


def run_perp_pair_backtest(
    algorithm: PairTradingAlgorithm,
    dominant_bars: list[dict[str, Any]],
    hedge_bars: list[dict[str, Any]],
    *,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    hedge_ratio: float = 1.0,
    position_fraction: float = 0.5,
    sizing_model: PairSizingModel | None = None,
    leverage: float = 1.0,
    funding_rates: dict[int, tuple[float, float]] | None = None,
    simulate_legging_failure: bool = False,
    legging_latency_bars: int = 0,
    spread_pct: float = 0.0,
    check_cointegration_breakdown: bool = False,
    cointegration_monitor: Any | None = None,
    reset_algorithm: bool = True,
    execution: Literal["next_open", "close"] = "close",
    liquidate_on_end: bool = True,
    **kwargs: Any,
) -> PairBacktestResult:
    """
    Hyperliquid-style perp pair backtest: long/short legs (signed coin size), no spot short constraint.
    """
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if not 0 < position_fraction <= 1:
        raise ValueError("position_fraction must be in (0, 1]")
    if leverage < 1.0:
        raise ValueError("leverage must be >= 1.0")

    effective_hedge_ratio = (
        getattr(algorithm, "hedge_ratio", hedge_ratio)
        if hedge_ratio == 1.0 and getattr(algorithm, "hedge_ratio", 1.0) != 1.0
        else hedge_ratio
    )
    effective_intercept = getattr(algorithm, "intercept", 0.0)
    effective_rolling_ols = getattr(algorithm, "rolling_ols", False)
    effective_sizing_model = sizing_model or getattr(algorithm, "sizing_model", "hedge_ratio")

    aligned = [normalize_bar(bar) for bar in align_bars_by_timestamp(dominant_bars, hedge_bars)]
    if not aligned:
        raise ValueError("no aligned bars for pair backtest")

    if reset_algorithm:
        algorithm.reset()

    cash = initial_cash
    dominant_position = 0.0
    dominant_entry_price = 0.0
    hedge_position = 0.0
    hedge_entry_price = 0.0
    spread_state: Literal["flat", "long_spread", "short_spread"] = "flat"
    total_fees = 0.0
    total_slippage_cost = 0.0
    total_funding_paid = 0.0
    total_funding_received = 0.0
    breakdown_events: list[dict[str, Any]] = []
    coint_monitor = None
    if check_cointegration_breakdown:
        if cointegration_monitor is not None:
            coint_monitor = cointegration_monitor
        else:
            from traderbot.risk.cointegration_monitor import CointegrationHealthMonitor
            coint_monitor = CointegrationHealthMonitor(min_observations=max(10, algorithm.lookback_period // 2))
    trades: list[PairTrade] = []
    equity_curve: list[tuple[int, float]] = []
    spread_curve: list[tuple[int, float]] = []
    z_score_curve: list[tuple[int, float]] = []
    exposure_curve: list[tuple[int, float]] = []
    gross_exposure_curve: list[tuple[int, float]] = []
    net_exposure_curve: list[tuple[int, float]] = []
    dominant_history: list[float] = []
    hedge_history: list[float] = []
    entry_equity: float | None = None
    round_trips = 0
    winning_trips = 0

    def equity_at(close_d: float, close_h: float) -> float:
        upnl_d = dominant_position * (close_d - dominant_entry_price) if dominant_position != 0 else 0.0
        upnl_h = hedge_position * (close_h - hedge_entry_price) if hedge_position != 0 else 0.0
        return cash + upnl_d + upnl_h

    def adjust_position(
        timestamp: int,
        leg: Literal["dominant", "hedge"],
        price: float,
        target_delta_coins: float,
    ) -> None:
        nonlocal cash, dominant_position, dominant_entry_price, hedge_position, hedge_entry_price, total_fees, total_slippage_cost
        if target_delta_coins == 0:
            return
        action: PairLegAction = "buy" if target_delta_coins > 0 else "sell"
        fill = simulated_fill_price(action, price, qty=abs(target_delta_coins), spread_pct=spread_pct, slippage_rate=slippage_rate)
        slippage_cost = abs(target_delta_coins) * abs(fill - price)
        total_slippage_cost += slippage_cost
        notional = abs(target_delta_coins) * fill
        fee = notional * fee_rate
        total_fees += fee
        cash -= fee

        curr_pos = dominant_position if leg == "dominant" else hedge_position
        curr_entry = dominant_entry_price if leg == "dominant" else hedge_entry_price

        if curr_pos == 0:
            new_pos = target_delta_coins
            new_entry = fill
        elif (curr_pos > 0 and target_delta_coins > 0) or (curr_pos < 0 and target_delta_coins < 0):
            new_pos = curr_pos + target_delta_coins
            new_entry = (abs(curr_pos) * curr_entry + abs(target_delta_coins) * fill) / abs(new_pos)
        else:
            # Reducing, closing, or flipping
            closed_size = min(abs(curr_pos), abs(target_delta_coins))
            if curr_pos > 0:
                # Closing long
                realized_pnl = closed_size * (fill - curr_entry)
            else:
                # Closing short
                realized_pnl = closed_size * (curr_entry - fill)
            cash += realized_pnl
            new_pos = curr_pos + target_delta_coins
            if abs(new_pos) < 1e-12:
                new_pos = 0.0
                new_entry = 0.0
            elif (curr_pos > 0 and new_pos > 0) or (curr_pos < 0 and new_pos < 0):
                # Partially closed, same side
                new_entry = curr_entry
            else:
                # Flipped side
                new_entry = fill

        if leg == "dominant":
            dominant_position = new_pos
            dominant_entry_price = new_entry
        else:
            hedge_position = new_pos
            hedge_entry_price = new_entry

        beta_exp = (dominant_position * price) + (hedge_position * price / effective_hedge_ratio)
        trades.append(
            PairTrade(
                timestamp,
                leg,
                action,
                fill,
                abs(target_delta_coins),
                fee,
                notional=notional,
                beta_exposure=beta_exp,
            )
        )

    def close_all(timestamp: int, close_d: float, close_h: float) -> None:
        nonlocal dominant_position, hedge_position
        if dominant_position != 0:
            adjust_position(timestamp, "dominant", close_d, -dominant_position)
        if hedge_position != 0:
            adjust_position(timestamp, "hedge", close_h, -hedge_position)

    pending_perp_action: tuple[str, Any] | None = None
    delayed_hedge_entry: tuple[int, float] | None = None

    for bar_index, bar in enumerate(aligned):
        timestamp = int(bar["timestamp"])
        open_d = float(bar.get("open", bar["close"]))
        open_h = float(bar.get("hedge_open", bar["hedge_close"]))
        close_d = float(bar["close"])
        close_h = float(bar["hedge_close"])
        dominant_history.append(close_d)
        hedge_history.append(close_h)

        # 1. Next open execution of pending orders
        if execution == "next_open" and pending_perp_action is not None:
            action_type, payload = pending_perp_action
            if action_type == "close_spread":
                delayed_hedge_entry = None
                close_all(timestamp, open_d, open_h)
                spread_state = "flat"
                if entry_equity is not None:
                    round_trips += 1
                    if equity_at(open_d, open_h) > entry_equity:
                        winning_trips += 1
                    entry_equity = None
            elif action_type == "entry":
                sizing, direction = payload
                entry_equity = equity_at(open_d, open_h)
                if simulate_legging_failure:
                    adjust_position(timestamp, "dominant", open_d, sizing.leg_a_qty)
                    adjust_position(timestamp, "dominant", open_d, -dominant_position)
                    algorithm.state_manager.confirm_entry_filled(leg_a_filled=True, leg_b_filled=False)
                    spread_state = "flat"
                elif legging_latency_bars > 0:
                    adjust_position(timestamp, "dominant", open_d, sizing.leg_a_qty)
                    delayed_hedge_entry = (bar_index + legging_latency_bars, sizing.leg_b_qty)
                    spread_state = direction
                else:
                    adjust_position(timestamp, "dominant", open_d, sizing.leg_a_qty)
                    adjust_position(timestamp, "hedge", open_h, sizing.leg_b_qty)
                    spread_state = direction
            pending_perp_action = None

        # 1b. Check delayed hedge fill from legging latency
        if delayed_hedge_entry is not None and bar_index >= delayed_hedge_entry[0]:
            target_hedge_qty = delayed_hedge_entry[1]
            exec_price_h = open_h if execution == "next_open" else close_h
            adjust_position(timestamp, "hedge", exec_price_h, target_hedge_qty)
            delayed_hedge_entry = None

        # 2. Funding rate cash adjustments for perpetual futures
        if funding_rates and timestamp in funding_rates:
            rate_d, rate_h = funding_rates[timestamp]
            funding_d = dominant_position * close_d * rate_d
            funding_h = hedge_position * close_h * rate_h
            for payment in (funding_d, funding_h):
                if payment > 0:
                    total_funding_paid += payment
                elif payment < 0:
                    total_funding_received += abs(payment)
            cash -= (funding_d + funding_h)

        snapshot = spread_z_score_from_closes(
            np.asarray(dominant_history, dtype=float),
            np.asarray(hedge_history, dtype=float),
            lookback_period=algorithm.lookback_period,
            model=algorithm.spread_model,
            hedge_ratio=effective_hedge_ratio,
            intercept=effective_intercept,
            rolling_ols=effective_rolling_ols,
        )
        if snapshot is not None:
            spread_curve.append((timestamp, snapshot.spread_pct))
            z_score_curve.append((timestamp, snapshot.z_score))

        # Cointegration breakdown check
        is_coint_broken = False
        if coint_monitor is not None and len(dominant_history) >= algorithm.lookback_period:
            health = coint_monitor.evaluate_pair_health(
                dominant_history[-algorithm.lookback_period:],
                hedge_history[-algorithm.lookback_period:],
                hedge_ratio=effective_hedge_ratio,
            )
            if health.is_broken:
                is_coint_broken = True
                breakdown_events.append({
                    "timestamp": timestamp,
                    "reasons": list(health.reasons),
                    "pvalue": health.cointegration_pvalue,
                })
                if spread_state != "flat":
                    delayed_hedge_entry = None
                    close_all(timestamp, close_d, close_h)
                    spread_state = "flat"

        signal: PairSignal = algorithm.pair_signal(bar)
        equity = equity_at(close_d, close_h)

        if len(dominant_history) >= algorithm.lookback_period:
            if not is_coint_broken and signal in ("long_spread", "short_spread") and spread_state == "flat":
                direction = "long_spread" if signal == "long_spread" else "short_spread"
                current_spread_std = snapshot.spread_std if snapshot is not None else None
                sizing = calculate_pair_position_sizes(
                    capital=equity,
                    close_a=close_d,
                    close_b=close_h,
                    hedge_ratio=effective_hedge_ratio,
                    sizing_model=effective_sizing_model,
                    position_fraction=position_fraction,
                    spread_std=current_spread_std,
                    leverage=leverage,
                    direction=direction,
                )
                if execution == "next_open":
                    pending_perp_action = ("entry", (sizing, direction))
                else:
                    entry_equity = equity
                    if simulate_legging_failure:
                        # Leg A fills, Leg B fails: execute Leg A, then immediately unwind Leg A per policy
                        adjust_position(timestamp, "dominant", close_d, sizing.leg_a_qty)
                        adjust_position(timestamp, "dominant", close_d, -dominant_position)
                        algorithm.state_manager.confirm_entry_filled(leg_a_filled=True, leg_b_filled=False)
                        spread_state = "flat"
                    elif legging_latency_bars > 0:
                        adjust_position(timestamp, "dominant", close_d, sizing.leg_a_qty)
                        delayed_hedge_entry = (bar_index + legging_latency_bars, sizing.leg_b_qty)
                        spread_state = direction
                    else:
                        adjust_position(timestamp, "dominant", close_d, sizing.leg_a_qty)
                        adjust_position(timestamp, "hedge", close_h, sizing.leg_b_qty)
                        spread_state = direction
            elif signal == "close_spread" and spread_state != "flat":
                delayed_hedge_entry = None
                if execution == "next_open":
                    pending_perp_action = ("close_spread", None)
                else:
                    close_all(timestamp, close_d, close_h)
                    spread_state = "flat"
                    if entry_equity is not None:
                        round_trips += 1
                        if equity_at(close_d, close_h) > entry_equity:
                            winning_trips += 1
                        entry_equity = None
                        entry_equity = None

        curr_eq = equity_at(close_d, close_h)
        equity_curve.append((timestamp, curr_eq))
        net_exposure = dominant_position * close_d + hedge_position * close_h
        gross_exposure = abs(dominant_position) * close_d + abs(hedge_position) * close_h
        exposure_curve.append((timestamp, net_exposure))
        net_exposure_curve.append((timestamp, net_exposure))
        gross_exposure_curve.append((timestamp, gross_exposure))

    last_close_d = dominant_history[-1] if dominant_history else 0.0
    last_close_h = hedge_history[-1] if hedge_history else 0.0
    last_timestamp = int(aligned[-1]["timestamp"]) if aligned else 0
    marked_equity = equity_at(last_close_d, last_close_h)

    has_open_positions = (abs(dominant_position) > 1e-12 or abs(hedge_position) > 1e-12)
    if has_open_positions and liquidate_on_end:
        close_all(last_timestamp, last_close_d, last_close_h)
        liquidated_equity = cash
        final_equity = liquidated_equity
        if equity_curve:
            equity_curve[-1] = (last_timestamp, final_equity)
            exposure_curve[-1] = (last_timestamp, 0.0)
            net_exposure_curve[-1] = (last_timestamp, 0.0)
            gross_exposure_curve[-1] = (last_timestamp, 0.0)
        else:
            equity_curve.append((last_timestamp, final_equity))
            exposure_curve.append((last_timestamp, 0.0))
            net_exposure_curve.append((last_timestamp, 0.0))
            gross_exposure_curve.append((last_timestamp, 0.0))
    else:
        exit_fill_d = _fill_price(last_close_d, "sell" if dominant_position > 0 else "buy", slippage_rate)
        exit_fill_h = _fill_price(last_close_h, "sell" if hedge_position > 0 else "buy", slippage_rate)
        est_exit_fees = (abs(dominant_position) * exit_fill_d + abs(hedge_position) * exit_fill_h) * fee_rate
        pnl_d = dominant_position * (exit_fill_d - dominant_entry_price) if dominant_position != 0 else 0.0
        pnl_h = hedge_position * (exit_fill_h - hedge_entry_price) if hedge_position != 0 else 0.0
        liquidated_equity = cash + pnl_d + pnl_h - est_exit_fees
        final_equity = marked_equity

    total_funding = total_funding_paid - total_funding_received
    win_rate_pct = round(winning_trips / round_trips * 100.0, 2) if round_trips > 0 else None
    return PairBacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        trades=trades,
        equity_curve=equity_curve,
        spread_curve=spread_curve,
        z_score_curve=z_score_curve,
        exposure_curve=exposure_curve,
        gross_exposure_curve=gross_exposure_curve,
        net_exposure_curve=net_exposure_curve,
        fee_rate=fee_rate,
        total_fees=total_fees,
        total_slippage_cost=total_slippage_cost,
        total_funding=total_funding,
        total_funding_paid=total_funding_paid,
        total_funding_received=total_funding_received,
        marked_equity=marked_equity,
        liquidated_equity=liquidated_equity,
        win_rate_pct=win_rate_pct,
        sizing_model=effective_sizing_model,
        spread_model=algorithm.spread_model,
        execution=execution,
        breakdown_events=breakdown_events,
    )


def run_multi_pair_backtest(
    pairs_config: list[dict[str, Any]],
    *,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    **kwargs: Any,
) -> MultiPairBacktestResult:
    """Run concurrent backtests across multiple pairs sharing total initial capital."""
    if not pairs_config:
        raise ValueError("pairs_config must not be empty")
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")

    pair_results: dict[str, PairBacktestResult] = {}
    total_weights = sum(float(p.get("weight", 1.0)) for p in pairs_config)
    if total_weights <= 0:
        total_weights = float(len(pairs_config))

    total_fees = 0.0
    total_funding = 0.0
    total_slippage = 0.0
    all_timestamps: set[int] = set()

    for index, pair_conf in enumerate(pairs_config):
        pair_id = str(pair_conf.get("pair_id", f"pair_{index}"))
        weight = float(pair_conf.get("weight", 1.0)) / total_weights
        pair_cash = initial_cash * weight
        algo = pair_conf["algorithm"]
        dominant_bars = pair_conf["dominant_bars"]
        hedge_bars = pair_conf["hedge_bars"]
        p_fee = float(pair_conf.get("fee_rate", fee_rate))
        p_slip = float(pair_conf.get("slippage_rate", slippage_rate))
        p_mode = pair_conf.get("mode", "perp")

        extra_args = {
            **kwargs,
            **{
                k: v
                for k, v in pair_conf.items()
                if k not in ("pair_id", "algorithm", "dominant_bars", "hedge_bars", "weight", "fee_rate", "slippage_rate", "mode")
            },
        }

        if p_mode == "spot":
            p_res = run_pair_backtest(
                algo, dominant_bars, hedge_bars, initial_cash=pair_cash, fee_rate=p_fee, slippage_rate=p_slip, **extra_args
            )
        else:
            p_res = run_perp_pair_backtest(
                algo, dominant_bars, hedge_bars, initial_cash=pair_cash, fee_rate=p_fee, slippage_rate=p_slip, **extra_args
            )
        pair_results[pair_id] = p_res
        total_fees += p_res.total_fees
        total_funding += p_res.total_funding
        total_slippage += p_res.total_slippage_cost
        for ts, _ in p_res.equity_curve:
            all_timestamps.add(ts)

    sorted_timestamps = sorted(all_timestamps)
    portfolio_equity_curve: list[tuple[int, float]] = []
    portfolio_exposure_curve: list[tuple[int, float]] = []

    # Pre-index curves for fast lookup
    pair_equity_maps = {pid: dict(res.equity_curve) for pid, res in pair_results.items()}
    pair_exp_maps = {pid: dict(res.exposure_curve) for pid, res in pair_results.items()}

    last_known_eq = {pid: res.initial_cash for pid, res in pair_results.items()}
    last_known_exp = {pid: 0.0 for pid in pair_results}

    for ts in sorted_timestamps:
        ts_equity = 0.0
        ts_exposure = 0.0
        for pid in pair_results:
            if ts in pair_equity_maps[pid]:
                last_known_eq[pid] = pair_equity_maps[pid][ts]
            if ts in pair_exp_maps[pid]:
                last_known_exp[pid] = pair_exp_maps[pid][ts]
            ts_equity += last_known_eq[pid]
            ts_exposure += last_known_exp[pid]
        portfolio_equity_curve.append((ts, ts_equity))
        portfolio_exposure_curve.append((ts, ts_exposure))

    final_equity = portfolio_equity_curve[-1][1] if portfolio_equity_curve else initial_cash

    return MultiPairBacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        pair_results=pair_results,
        portfolio_equity_curve=portfolio_equity_curve,
        portfolio_exposure_curve=portfolio_exposure_curve,
        total_fees=total_fees,
        total_funding=total_funding,
        total_slippage_cost=total_slippage,
    )


def run_pair_backtest_for_exchange(
    exchange: str,
    algorithm: PairTradingAlgorithm,
    dominant_bars: list[dict[str, Any]],
    hedge_bars: list[dict[str, Any]],
    *,
    fee_rate: float,
    slippage_rate: float,
    hedge_ratio: float = 1.0,
    initial_cash: float = DEFAULT_BACKTEST_INITIAL_CASH,
    **kwargs: Any,
) -> PairBacktestResult:
    from traderbot.markets.exchange import normalize_live_exchange

    venue = normalize_live_exchange(exchange)
    if venue == "hyperliquid":
        return run_perp_pair_backtest(
            algorithm,
            dominant_bars,
            hedge_bars,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            hedge_ratio=hedge_ratio,
            **kwargs,
        )
    return run_pair_backtest(
        algorithm,
        dominant_bars,
        hedge_bars,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        hedge_ratio=hedge_ratio,
        **kwargs,
    )
