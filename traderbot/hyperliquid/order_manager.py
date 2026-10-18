"""Live Hyperliquid execution for order-aware algorithms (limit entries, brackets, quotes).

Mirrors :class:`traderbot.backtesting.broker.SimBroker` one bar at a time:

1. resting orders placed at earlier closes are polled; a fill calls ``algorithm.on_fill``,
   cancels the other resting orders (OCO) and attaches the bracket from the **fill price**:
   a reduce-only post-only (ALO) take-profit limit plus a native reduce-only stop trigger;
2. a bracket leg that filled (position went flat) cancels its sibling;
3. the algorithm sees the closed bar; quotes are cancelled/replaced as ALO orders, limit
   entries rest as ALO for ``ttl_bars`` bars, market orders go out as IOC.

Every exchange call goes through ``api`` (the :mod:`traderbot.hyperliquid.trading`
functions by default) so the logic is testable without keys. Not exercised against the live
exchange in this repo's tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, OrderSpec, SignalAction
from traderbot.hyperliquid import trading as hl

logger = logging.getLogger(__name__)

EventSink = Callable[[dict[str, Any]], None]


def default_api() -> SimpleNamespace:
    return SimpleNamespace(
        account_value=hl.hyperliquid_account_value_usd,
        position_size=hl.hyperliquid_position_size,
        sz_decimals=hl.hyperliquid_sz_decimals,
        order_status=hl.hyperliquid_order_status,
        limit_order=hl.hyperliquid_limit_order,
        market_open=hl.hyperliquid_market_open,
        place_stop=hl.hyperliquid_place_stop,
        cancel=hl.hyperliquid_cancel_order,
    )


@dataclass
class LiveRestingOrder:
    oid: int | str
    side: SignalAction
    price: float
    size: float
    ttl: int
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None
    from_quote: bool = False
    reported_fill: float = 0.0


@dataclass
class LiveBracket:
    direction: int
    size: float
    take_profit_price: float | None
    stop_price: float | None
    tp_oid: int | str | None = None
    sl_oid: int | str | None = None


@dataclass
class HyperliquidOrderManager:
    coin: str
    algorithm: Algorithm
    allow_short: bool = False
    capital_cap: float | None = None
    api: Any = field(default_factory=default_api)
    emit: EventSink = lambda _event: None
    resting: list[LiveRestingOrder] = field(default_factory=list)
    bracket: LiveBracket | None = None
    position: float = 0.0
    _decimals: int | None = None

    # --- helpers --------------------------------------------------------------------------

    @property
    def decimals(self) -> int:
        if self._decimals is None:
            self._decimals = int(self.api.sz_decimals(self.coin))
        return self._decimals

    def _equity(self) -> float:
        value = float(self.api.account_value())
        if self.capital_cap is not None and self.capital_cap > 0:
            return min(value, float(self.capital_cap))
        return value

    def _units_for(self, side: SignalAction, size: OrderSize | None, price: float) -> tuple[float, bool]:
        """(order units, reduce_only) to move toward the algorithm's target exposure."""
        if size is None or size.target_exposure is None:
            target = (1.0 if side == "buy" else (-1.0 if self.allow_short and self.position <= 0 else 0.0))
            if side == "buy" and self.position < 0:
                target = 0.0
        else:
            target = float(size.target_exposure)
            if not self.allow_short:
                target = max(0.0, target)
        target_units = target * self._equity() / price if target != 0 else 0.0
        delta = target_units - self.position
        if side == "buy" and delta <= 0 or side == "sell" and delta >= 0:
            return 0.0, False
        reduce_only = target_units == 0.0 or (abs(target_units) < abs(self.position) and target_units * self.position >= 0)
        return abs(delta), reduce_only

    def _round_px(self, price: float, *, side: SignalAction) -> float:
        # Maker prices round away from the touch (buy down, sell up) so ALO is not rejected.
        return hl.round_hyperliquid_price(price, self.decimals, round_up=(side == "sell"))

    def _cancel(self, oid: int | str | None) -> None:
        if oid is None:
            return
        try:
            self.api.cancel(self.coin, oid)
        except (hl.HyperliquidTradingError, ValueError) as exc:
            # Already filled/cancelled orders cannot be cancelled; the next poll reconciles.
            logger.info("cancel %s on %s: %s", oid, self.coin, exc)

    def _refresh_position(self) -> float:
        self.position = float(self.api.position_size(self.coin))
        return self.position

    # --- phases ---------------------------------------------------------------------------

    def _attach_bracket(self, direction: int, fill_price: float, size: float, tp: float | None, sl: float | None) -> None:
        if (tp is None and sl is None) or size <= 0:
            return
        bracket = LiveBracket(
            direction=direction,
            size=size,
            take_profit_price=fill_price * (1 + direction * tp) if tp else None,
            stop_price=fill_price * (1 - direction * sl) if sl else None,
        )
        exit_buy = direction < 0
        if bracket.take_profit_price:
            try:
                response = self.api.limit_order(
                    self.coin,
                    is_buy=exit_buy,
                    size=size,
                    price=self._round_px(bracket.take_profit_price, side="buy" if exit_buy else "sell"),
                    post_only=True,
                    reduce_only=True,
                )
                bracket.tp_oid = hl.hyperliquid_order_id(response)
            except hl.HyperliquidTradingError as exc:
                self.emit({"event": "bracket_error", "leg": "take_profit", "message": str(exc)})
        if bracket.stop_price:
            try:
                response = self.api.place_stop(
                    self.coin, size=size, trigger_price=bracket.stop_price, is_buy=exit_buy, sz_decimals=self.decimals
                )
                bracket.sl_oid = hl.hyperliquid_order_id(response)
            except hl.HyperliquidTradingError as exc:
                self.emit({"event": "bracket_error", "leg": "stop_loss", "message": str(exc)})
        self.bracket = bracket
        self.emit({"event": "bracket_placed", "tp": bracket.take_profit_price, "stop": bracket.stop_price,
                   "tp_oid": bracket.tp_oid, "sl_oid": bracket.sl_oid})

    def _clear_bracket(self) -> None:
        if self.bracket is not None:
            self._cancel(self.bracket.tp_oid)
            self._cancel(self.bracket.sl_oid)
        self.bracket = None

    def _poll_resting(self, close_price: float) -> None:
        if not self.resting:
            return
        still: list[LiveRestingOrder] = []
        filled_one = False
        for order in self.resting:
            status = self.api.order_status(order.oid)
            new_fill = max(0.0, status.filled_size - order.reported_fill)
            done = status.status not in ("open", "resting", "triggered")
            if new_fill > 0:
                order.reported_fill += new_fill
                position = self._refresh_position()
                price = status.avg_price or order.price
                self.algorithm.on_fill(order.side, price, new_fill, "limit", position)
                self.emit({"event": "fill", "side": order.side, "price": price, "size": new_fill,
                           "liquidity": "maker", "oid": order.oid, "position": position})
                if order.take_profit_pct is not None or order.stop_loss_pct is not None:
                    self._clear_bracket()
                    direction = 1 if position > 0 else -1 if position < 0 else 0
                    if direction == (1 if order.side == "buy" else -1):
                        self._attach_bracket(direction, price, abs(position), order.take_profit_pct, order.stop_loss_pct)
                filled_one = True
            if done:
                if order.reported_fill == 0 and not order.from_quote:
                    self.algorithm.on_order_expired(order.side)
                continue
            order.ttl -= 1
            if order.ttl <= 0 or filled_one:
                self._cancel(order.oid)
                if order.reported_fill == 0 and not order.from_quote:
                    self.algorithm.on_order_expired(order.side)
                continue
            still.append(order)
        if filled_one:  # OCO: one fill cancels the other resting orders
            for order in still:
                self._cancel(order.oid)
                if not order.from_quote:
                    self.algorithm.on_order_expired(order.side)
            still = []
        self.resting = still

    def _poll_bracket(self, close_price: float) -> None:
        if self.bracket is None:
            return
        position = self._refresh_position()
        if position != 0 and (position > 0) == (self.bracket.direction > 0):
            return
        reason, price = "stop_loss", self.bracket.stop_price or close_price
        if self.bracket.tp_oid is not None:
            tp_status = self.api.order_status(self.bracket.tp_oid)
            if tp_status.status == "filled":
                reason, price = "take_profit", tp_status.avg_price or self.bracket.take_profit_price or close_price
        side: SignalAction = "sell" if self.bracket.direction > 0 else "buy"
        self.algorithm.on_fill(side, price, self.bracket.size, reason, position)
        self.emit({"event": "fill", "side": side, "price": price, "size": self.bracket.size, "reason": reason,
                   "liquidity": "maker" if reason == "take_profit" else "taker", "position": position})
        self._clear_bracket()

    def _place_limit(self, side: SignalAction, price: float, size: OrderSize | None, *, ttl: int,
                     tp: float | None, sl: float | None, from_quote: bool) -> None:
        units, reduce_only = self._units_for(side, size, price)
        if units <= 0:
            return
        try:
            units = hl.prepare_order_size(self.coin, units, price=price, reduce_only=reduce_only,
                                          sz_decimals=self.decimals)
            response = self.api.limit_order(self.coin, is_buy=side == "buy", size=units,
                                            price=self._round_px(price, side=side), post_only=True,
                                            reduce_only=reduce_only)
        except hl.HyperliquidTradingError as exc:
            # e.g. ALO would have crossed: treat like the backtest's rejected post-only order.
            self.emit({"event": "order_rejected", "side": side, "price": price, "message": str(exc)})
            if not from_quote:
                self.algorithm.on_order_expired(side)
            return
        oid = hl.hyperliquid_order_id(response)
        status = hl.first_order_status(response)
        order = LiveRestingOrder(oid=oid, side=side, price=price, size=units, ttl=ttl, take_profit_pct=tp,
                                 stop_loss_pct=sl, from_quote=from_quote)
        if status.status == "filled":  # cannot happen with ALO, but be safe
            order.ttl = 1
        self.resting.append(order)
        self.emit({"event": "order_resting", "side": side, "price": price, "size": units, "oid": oid,
                   "quote": from_quote})

    def _market(self, side: SignalAction, size: OrderSize | None, spec: OrderSpec | None, close_price: float) -> None:
        units, reduce_only = self._units_for(side, size, close_price)
        if units <= 0:
            return
        units = hl.prepare_order_size(self.coin, units, price=close_price, reduce_only=reduce_only,
                                      sz_decimals=self.decimals)
        if reduce_only:
            self._clear_bracket()
        response = self.api.market_open(self.coin, is_buy=side == "buy", size=units)
        status = hl.first_order_status(response)
        if status.status != "filled" or status.filled_size <= 0:
            raise hl.HyperliquidTradingError(f"{self.coin} market order not filled (status={status.status})")
        position = self._refresh_position()
        self.algorithm.on_fill(side, status.avg_price, status.filled_size, "market", position)
        self.emit({"event": "fill", "side": side, "price": status.avg_price, "size": status.filled_size,
                   "liquidity": "taker", "position": position})
        if position == 0:
            self._clear_bracket()
        elif spec is not None and spec.has_bracket:
            direction = 1 if position > 0 else -1
            if direction == (1 if side == "buy" else -1):
                self._clear_bracket()
                self._attach_bracket(direction, status.avg_price, abs(position), spec.take_profit_pct,
                                     spec.stop_loss_pct)

    def step(self, bar: Bar) -> SignalAction:
        close_price = float(bar["close"])
        self._poll_resting(close_price)
        self._poll_bracket(close_price)
        algorithm = self.algorithm
        signal = algorithm.on_bar(bar)
        size = algorithm.order_size() if signal != "hold" else None
        spec = algorithm.order_spec() if signal != "hold" else None
        quotes = algorithm.quotes()
        if quotes is not None:
            for order in [o for o in self.resting if o.from_quote]:
                self._cancel(order.oid)
            self.resting = [o for o in self.resting if not o.from_quote]
            for quote in quotes:
                self._place_limit(quote.side, float(quote.limit_price), OrderSize(target_exposure=quote.target_exposure),
                                  ttl=1, tp=quote.take_profit_pct, sl=quote.stop_loss_pct, from_quote=True)
        if signal == "hold":
            return signal
        for order in [o for o in self.resting if not o.from_quote]:
            self._cancel(order.oid)
        self.resting = [o for o in self.resting if o.from_quote]
        if spec is not None and spec.order_type == "limit":
            self._place_limit(signal, float(spec.limit_price or 0.0), size, ttl=spec.ttl_bars,
                              tp=spec.take_profit_pct, sl=spec.stop_loss_pct, from_quote=False)
        else:
            self._market(signal, size, spec, close_price)
        return signal

    def cancel_all(self) -> None:
        for order in self.resting:
            self._cancel(order.oid)
        self.resting = []
        self._clear_bracket()
