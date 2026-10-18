from __future__ import annotations

from collections.abc import Callable

from traderbot.algorithms.base import Bar, SignalAction
from traderbot.terminal.events import print_signal_event, print_tick_event
from traderbot.terminal.paper_portfolio import PaperPortfolio
from traderbot.traders.position import order_action_for_long_only
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


class TerminalAlgorithmTrader(AlgorithmTrader):
    """Paper/live trader that logs each signal as a JSON line on stdout."""

    strategy_id: str | None = None
    emit_holds = False
    paper_portfolio: PaperPortfolio | None = None
    _last_mark_price: float | None = None
    _last_bar_timestamp: int | None = None
    _refresh_mark_price: Callable[[], float | None] | None = None

    def _attach_paper_portfolio(self, payload: dict[str, object]) -> None:
        if self.paper_portfolio is None or self._last_mark_price is None:
            return
        payload["portfolio"] = self.paper_portfolio.snapshot(self._last_mark_price)

    def _sync_mark_from_closed_bar(self) -> None:
        if self._refresh_mark_price is None:
            return
        try:
            fresh = self._refresh_mark_price()
        except Exception:
            return
        if fresh is not None and fresh > 0:
            self._last_mark_price = float(fresh)

    def _attach_last_bar_quote(self, payload: dict[str, object]) -> None:
        if self.market_symbol:
            payload["symbol"] = self.market_symbol
        if self._last_mark_price is not None:
            payload["close"] = self._last_mark_price
        if self._last_bar_timestamp is not None:
            payload["bar_timestamp"] = self._last_bar_timestamp

    def step(self) -> None:
        poll = getattr(self, "_poll_count", 0) + 1
        self._poll_count = poll

        bar = self.bar_source() if self.bar_source else None
        if bar is None:
            self._sync_mark_from_closed_bar()
            tick_no_bar: dict[str, object] = {
                "event": "tick",
                "poll": poll,
                "status": "no_new_bar",
                "strategy_id": self.strategy_id,
            }
            self._attach_last_bar_quote(tick_no_bar)
            self._attach_paper_portfolio(tick_no_bar)
            print_tick_event(tick_no_bar)
            return

        self._last_mark_price = float(bar.get("close") or 0)
        timestamp = bar.get("timestamp")
        if timestamp is not None:
            self._last_bar_timestamp = int(timestamp)
        self.prepare_for_bar(bar)
        signal = self.algorithm.on_bar(bar)
        self._pending_order_size = self.algorithm.order_size() if signal != "hold" else None
        order_action = order_action_for_long_only(self.in_position, signal)

        if order_action is None:
            tick: dict[str, object] = {
                "event": "tick",
                "poll": poll,
                "status": "evaluated",
                "strategy_id": self.strategy_id,
                "bar_timestamp": bar.get("timestamp"),
                "close": bar.get("close"),
                "symbol": bar.get("symbol"),
                "signal": signal,
                "in_position": self.in_position,
                "order": None,
            }
            if signal == "hold" and self.emit_holds:
                print_signal_event(
                    signal,
                    bar,
                    mode=self.execution.mode,
                    strategy_id=self.strategy_id,
                    emit_holds=True,
                )
            else:
                self._attach_paper_portfolio(tick)
                print_tick_event(tick)
            return

        if not self.execution.permits(order_action):
            print_tick_event(
                {
                    "event": "tick",
                    "poll": poll,
                    "status": "blocked",
                    "strategy_id": self.strategy_id,
                    "bar_timestamp": bar.get("timestamp"),
                    "close": bar.get("close"),
                    "symbol": bar.get("symbol"),
                    "signal": signal,
                    "in_position": self.in_position,
                    "order": order_action,
                },
            )
            return

        if self.execution.mode == "paper":
            self.on_paper_signal(order_action, bar)
            self._sync_in_position_after_paper_fill(order_action)
        else:
            self.on_signal(order_action, bar)

    def _sync_in_position_after_paper_fill(self, action: SignalAction) -> None:
        if self.paper_portfolio is not None:
            self.in_position = self.paper_portfolio.base_amount > 0
        else:
            self._apply_position_after_fill(action)

    def on_paper_signal(self, action: SignalAction, bar: Bar) -> None:
        extra: dict[str, object] | None = None
        if self.paper_portfolio is not None:
            price = float(bar.get("close") or 0)
            max_quote_spend: float | None = None
            if action == "buy":
                wallet_quote = self.paper_portfolio.quote_cash
                max_quote_spend = self.inventory.spendable_quote(wallet_quote)
            fill = self.paper_portfolio.apply_fill(
                action,
                price,
                order_size=self._pending_order_size,
                max_quote_spend=max_quote_spend,
            )
            if fill.get("filled"):
                if action == "buy":
                    quote_spent = float(fill.get("quote_spent") or 0.0)
                    base_delta = float(fill.get("base_delta") or 0.0)
                    if quote_spent > 0 and base_delta > 0:
                        self.inventory.record_buy(
                            quote_spent=quote_spent,
                            base_received=base_delta,
                            price=price,
                        )
                elif action == "sell":
                    base_sold = abs(float(fill.get("base_delta") or 0.0))
                    if base_sold > 0:
                        self.inventory.record_sell(base_sold=base_sold)
            extra = {"fill": fill, "portfolio": self.paper_portfolio.snapshot(price)}
        print_signal_event(
            action,
            bar,
            mode="paper",
            strategy_id=self.strategy_id,
            emit_holds=self.emit_holds,
            extra=extra,
        )

    def on_signal(self, action: SignalAction, bar: Bar) -> None:
        print_signal_event(
            action,
            bar,
            mode="live",
            strategy_id=self.strategy_id,
            emit_holds=self.emit_holds,
        )
        try:
            AlgorithmTrader.on_signal(self, action, bar)
        except Exception as exc:
            print_tick_event(
                {
                    "event": "order_error",
                    "strategy_id": self.strategy_id,
                    "symbol": bar.get("symbol"),
                    "action": action,
                    "message": str(exc),
                },
            )
            raise
