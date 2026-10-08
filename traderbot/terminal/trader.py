from __future__ import annotations

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

    def _attach_paper_portfolio(self, payload: dict[str, object]) -> None:
        if self.paper_portfolio is None or self._last_mark_price is None:
            return
        payload["portfolio"] = self.paper_portfolio.snapshot(self._last_mark_price)

    def step(self) -> None:
        poll = getattr(self, "_poll_count", 0) + 1
        self._poll_count = poll

        bar = self.bar_source() if self.bar_source else None
        if bar is None:
            tick_no_bar: dict[str, object] = {
                "event": "tick",
                "poll": poll,
                "status": "no_new_bar",
                "strategy_id": self.strategy_id,
            }
            self._attach_paper_portfolio(tick_no_bar)
            print_tick_event(tick_no_bar)
            return

        self._last_mark_price = float(bar.get("close") or 0)
        signal = self.algorithm.on_bar(bar)
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
            self._apply_position_after_fill(order_action)
        else:
            self.on_signal(order_action, bar)

    def on_paper_signal(self, action: SignalAction, bar: Bar) -> None:
        extra: dict[str, object] | None = None
        if self.paper_portfolio is not None:
            price = float(bar.get("close") or 0)
            fill = self.paper_portfolio.apply_fill(action, price)
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
        AlgorithmTrader.on_signal(self, action, bar)
