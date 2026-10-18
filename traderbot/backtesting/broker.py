"""Simulated broker: one bar at a time, shared by :func:`run_backtest` and paper trading.

Per bar, in order:

1. market orders queued at the previous close (``execution="next_open"``) fill at the open;
2. bracket exits (stop first, then take-profit) for the position held into the bar;
3. resting limit orders / quotes placed at earlier closes fill if the bar trades through them;
4. the algorithm sees the closed bar and may queue new orders.

So nothing ever fills on information from the bar that produced the order.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from traderbot.algorithms.base import Algorithm, OrderSize, OrderSpec, SignalAction
from traderbot.backtesting.fills import Bracket, limit_fill_price, post_only_accepts
from traderbot.traders.order_sizing import MIN_ORDER_CASH, buy_quote_spend, sell_base_amount
from traderbot.utils.trading_costs import infer_exchange, maker_fee_for

logger = logging.getLogger(__name__)

EXECUTION_MODES = ("close", "next_open")


@dataclass
class RestingOrder:
    side: SignalAction
    limit_price: float
    size: OrderSize | None
    ttl: int
    post_only: bool = True
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None
    from_quote: bool = False


def fill_price_with_slippage(raw_price: float, action: SignalAction, slippage_rate: float) -> float:
    if action == "buy":
        return raw_price * (1.0 + slippage_rate)
    if action == "sell":
        return raw_price * (1.0 - slippage_rate)
    return raw_price


def shorts_allowed(algorithm: Algorithm, symbol: str | None, allow_short: bool | None) -> bool:
    wanted = bool(getattr(algorithm, "allow_short", False)) if allow_short is None else bool(allow_short)
    if not wanted:
        return False
    if infer_exchange(symbol) == "nobitex":
        logger.warning("shorts disabled: %s is a Nobitex spot market (long-only)", symbol)
        return False
    return True


def _target_exposure(action: SignalAction, size: OrderSize | None, position: float, shorts: bool) -> float:
    if size is None or size.target_exposure is None:
        if action == "buy":
            return 1.0 if position >= 0 else 0.0
        return -1.0 if (shorts and position <= 0) else 0.0
    target = float(size.target_exposure)
    return target if shorts else max(0.0, target)


class SimBroker:
    def __init__(
        self,
        algorithm: Algorithm,
        *,
        initial_cash: float,
        fee_rate: float = 0.0,
        slippage_rate: float = 0.0,
        execution: str = "next_open",
        maker_fee_rate: float | None = None,
        allow_short: bool | None = None,
        symbol: str | None = None,
    ):
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not 0 <= fee_rate < 1:
            raise ValueError("fee_rate must be in [0, 1)")
        if not 0 <= slippage_rate < 1:
            raise ValueError("slippage_rate must be in [0, 1)")
        if execution not in EXECUTION_MODES:
            raise ValueError(f"execution must be one of {EXECUTION_MODES}")
        maker_rate = maker_fee_for(fee_rate) if maker_fee_rate is None else float(maker_fee_rate)
        if not 0 <= maker_rate < 1:
            raise ValueError("maker_fee_rate must be in [0, 1)")
        self.algorithm = algorithm
        self.initial_cash = float(initial_cash)
        self.fee_rate = float(fee_rate)
        self.slippage_rate = float(slippage_rate)
        self.maker_rate = maker_rate
        self.execution = execution
        self.shorts = shorts_allowed(algorithm, symbol, allow_short)
        self.cash = float(initial_cash)
        self.position = 0.0
        self.total_fees = 0.0
        self.trades: list = []
        self.resting: list[RestingOrder] = []
        self.bracket: Bracket | None = None
        self.pending: tuple[SignalAction, OrderSize | None, OrderSpec | None] | None = None
        self.last_signal: SignalAction = "hold"

    # --- accounting -----------------------------------------------------------------------

    def equity(self, mark: float) -> float:
        return self.cash + self.position * mark

    def _record(self, ts: int, action: SignalAction, price: float, size: float, fee: float, cash_before: float,
                mark: float, reason: str, role: str) -> None:
        from traderbot.backtesting.engine import Trade

        self.trades.append(
            Trade(
                timestamp=ts,
                action=action,
                price=price,
                size=size,
                fee=fee,
                cash_before=cash_before,
                cash_after=self.cash,
                position_after=self.position,
                equity_after=self.cash + self.position * mark,
                reason=reason,
                liquidity=role,
            )
        )

    def _exact_fill(self, action: SignalAction, size: OrderSize | None, price: float, rate: float, *,
                    ts: int, mark: float, reason: str, role: str) -> float:
        """Trade toward a target exposure at ``price`` (fee on notional). Returns units traded."""
        if price <= 0:
            return 0.0
        equity = self.cash + self.position * price
        target_units = _target_exposure(action, size, self.position, self.shorts) * equity / price
        cash_before = self.cash
        if action == "buy":
            delta = target_units - self.position
            if target_units > 0:
                delta = min(delta, max(0.0, self.cash) / (price * (1.0 + rate)))
            if delta * price <= MIN_ORDER_CASH:
                return 0.0
            notional = delta * price
            fee = notional * rate
            self.cash -= notional + fee
            self.position += delta
        elif action == "sell":
            delta = self.position - target_units
            if not self.shorts:
                delta = min(delta, self.position)
            if delta * price <= MIN_ORDER_CASH:
                return 0.0
            notional = delta * price
            fee = notional * rate
            self.cash += notional - fee
            self.position -= delta
        else:
            return 0.0
        if abs(self.position) * price <= MIN_ORDER_CASH:
            self.position = 0.0
        self.total_fees += fee
        if self.position == 0.0:
            self.bracket = None
        self._record(ts, action, price, delta, fee, cash_before, mark, reason, role)
        self.algorithm.on_fill(action, price, delta, reason, self.position)  # type: ignore[arg-type]
        return delta

    def _legacy_fill(self, action: SignalAction, size: OrderSize | None, fill_price: float, *, ts: int,
                     mark: float) -> None:
        """Original long-only fill math (kept bit-for-bit for plain market strategies)."""
        if size is not None and action != "hold" and fill_price > 0:
            if action == "buy":
                spend = buy_quote_spend(size, cash=self.cash, position=self.position, fill_price=fill_price,
                                        initial_cash=self.initial_cash)
                if spend <= 0:
                    return
                fee = spend * self.fee_rate
                bought = (spend - fee) / fill_price
                cash_before = self.cash
                self.cash -= spend
                self.position += bought
                traded = bought
            elif action == "sell" and self.position > 0:
                sell_size = sell_base_amount(size, cash=self.cash, position=self.position, fill_price=fill_price)
                if sell_size <= 0:
                    return
                proceeds = sell_size * fill_price
                fee = proceeds * self.fee_rate
                remaining = self.position - sell_size
                if remaining * fill_price <= MIN_ORDER_CASH:
                    remaining = 0.0
                cash_before = self.cash
                self.cash += proceeds - fee
                self.position = remaining
                traded = sell_size
            else:
                return
            self.total_fees += fee
            self._record(ts, action, fill_price, traded, fee, cash_before, mark, "market", "taker")
            self.algorithm.on_fill(action, fill_price, traded, "market", self.position)
        elif action == "buy" and self.position == 0 and self.cash > 0 and fill_price > 0:
            cash_before = self.cash
            fee = cash_before * self.fee_rate
            self.total_fees += fee
            self.position = (cash_before - fee) / fill_price
            self.cash = 0.0
            self._record(ts, "buy", fill_price, self.position, fee, cash_before, mark, "market", "taker")
            self.algorithm.on_fill("buy", fill_price, self.position, "market", self.position)
        elif action == "sell" and self.position > 0 and fill_price > 0:
            cash_before = self.cash
            position_before = self.position
            proceeds = position_before * fill_price
            fee = proceeds * self.fee_rate
            self.total_fees += fee
            self.cash = proceeds - fee
            self.position = 0.0
            self._record(ts, "sell", fill_price, position_before, fee, cash_before, mark, "market", "taker")
            self.algorithm.on_fill("sell", fill_price, position_before, "market", 0.0)

    def _attach_bracket(self, take_profit_pct: float | None, stop_loss_pct: float | None, fill_price: float, *,
                        entry_direction: int) -> None:
        if (take_profit_pct is None and stop_loss_pct is None) or self.position == 0.0:
            return
        direction = 1 if self.position > 0 else -1
        if direction != entry_direction:
            return
        self.bracket = Bracket.from_fill(direction, fill_price, take_profit_pct=take_profit_pct,
                                         stop_loss_pct=stop_loss_pct)

    def market_fill(self, action: SignalAction, size: OrderSize | None, spec: OrderSpec | None, raw_price: float, *,
                    ts: int, mark: float) -> None:
        fill_price = fill_price_with_slippage(raw_price, action, self.slippage_rate)
        if spec is None and not self.shorts:
            self._legacy_fill(action, size, fill_price, ts=ts, mark=mark)
            return
        traded = self._exact_fill(action, size, fill_price, self.fee_rate, ts=ts, mark=mark, reason="market",
                                  role="taker")
        if traded > 0 and spec is not None:
            self._attach_bracket(spec.take_profit_pct, spec.stop_loss_pct, fill_price,
                                 entry_direction=1 if action == "buy" else -1)

    def _bracket_exit(self, bar: dict[str, Any], *, ts: int, mark: float, allow_take_profit: bool) -> None:
        if self.bracket is None or self.position == 0.0:
            return
        hit = self.bracket.exit_for_bar(bar, allow_take_profit=allow_take_profit)
        if hit is None:
            return
        raw_price, reason = hit
        side = self.bracket.exit_side
        flat = OrderSize(target_exposure=0.0)
        if reason == "stop_loss":
            self._exact_fill(side, flat, fill_price_with_slippage(raw_price, side, self.slippage_rate),
                             self.fee_rate, ts=ts, mark=mark, reason=reason, role="taker")
        else:
            self._exact_fill(side, flat, raw_price, self.maker_rate, ts=ts, mark=mark, reason=reason, role="maker")

    # --- per-bar phases -------------------------------------------------------------------

    def open_bar(self, bar: dict[str, Any]) -> None:
        """Phases 1-3: fills resting from earlier bars."""
        ts = int(bar["timestamp"])
        close_price = float(bar["close"])
        if self.execution == "next_open" and self.pending is not None:
            action, size, spec = self.pending
            self.pending = None
            if action != "hold":
                self.market_fill(action, size, spec, float(bar["open"]), ts=ts, mark=close_price)
        self._bracket_exit(bar, ts=ts, mark=close_price, allow_take_profit=True)
        if not self.resting:
            return
        still: list[RestingOrder] = []
        filled = False
        for order in self.resting:
            if filled:  # one fill per bar cancels the remaining resting orders (OCO)
                if not order.from_quote:
                    self.algorithm.on_order_expired(order.side)
                continue
            fill_px = limit_fill_price(order.side, order.limit_price, bar)
            if fill_px is not None:
                traded = self._exact_fill(order.side, order.size, fill_px, self.maker_rate, ts=ts, mark=close_price,
                                          reason="limit", role="maker")
                if traded > 0:
                    filled = True
                    self._attach_bracket(order.take_profit_pct, order.stop_loss_pct, fill_px,
                                         entry_direction=1 if order.side == "buy" else -1)
                    # Same-bar stop after the entry (conservative); no same-bar take-profit.
                    self._bracket_exit(bar, ts=ts, mark=close_price, allow_take_profit=False)
                elif not order.from_quote:
                    self.algorithm.on_order_expired(order.side)
                continue
            order.ttl -= 1
            if order.ttl > 0:
                still.append(order)
            elif not order.from_quote:
                self.algorithm.on_order_expired(order.side)
        self.resting = still

    def close_bar(self, bar: dict[str, Any]) -> SignalAction:
        """Phase 4: the algorithm sees the closed bar and queues orders."""
        ts = int(bar["timestamp"])
        close_price = float(bar["close"])
        algorithm = self.algorithm
        signal = algorithm.on_bar(bar)
        self.last_signal = signal
        size = algorithm.order_size() if signal != "hold" else None
        spec = algorithm.order_spec() if signal != "hold" else None
        quotes = algorithm.quotes()
        if quotes is not None:
            self.resting = [order for order in self.resting if not order.from_quote]
            for quote in quotes:
                if not post_only_accepts(quote.side, quote.limit_price, close_price):
                    continue
                self.resting.append(
                    RestingOrder(
                        side=quote.side,
                        limit_price=float(quote.limit_price),
                        size=OrderSize(target_exposure=quote.target_exposure),
                        ttl=1,
                        take_profit_pct=quote.take_profit_pct,
                        stop_loss_pct=quote.stop_loss_pct,
                        from_quote=True,
                    )
                )
        if signal == "hold":
            if self.execution == "next_open":
                self.pending = None
            return signal
        # A new signal replaces the strategy's earlier resting (non-quote) orders.
        self.resting = [order for order in self.resting if order.from_quote]
        if spec is not None and spec.order_type == "limit":
            limit_price = float(spec.limit_price or 0.0)
            if spec.post_only and not post_only_accepts(signal, limit_price, close_price):
                algorithm.on_order_expired(signal)
            else:
                self.resting.append(
                    RestingOrder(
                        side=signal,
                        limit_price=limit_price,
                        size=size,
                        ttl=spec.ttl_bars,
                        post_only=spec.post_only,
                        take_profit_pct=spec.take_profit_pct,
                        stop_loss_pct=spec.stop_loss_pct,
                    )
                )
        elif self.execution == "close":
            self.market_fill(signal, size, spec, close_price, ts=ts, mark=close_price)
        else:
            self.pending = (signal, size, spec)
        return signal

    def step(self, bar: dict[str, Any]) -> SignalAction:
        self.open_bar(bar)
        return self.close_bar(bar)
