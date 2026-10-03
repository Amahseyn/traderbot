from __future__ import annotations

from traderbot.algorithms.base import Bar, SignalAction
from traderbot.terminal.events import print_signal_event
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


class TerminalAlgorithmTrader(AlgorithmTrader):
    """Paper/live trader that logs each signal as a JSON line on stdout."""

    strategy_id: str | None = None
    emit_holds: bool = False

    def on_paper_signal(self, action: SignalAction, bar: Bar) -> None:
        print_signal_event(
            action,
            bar,
            mode="paper",
            strategy_id=self.strategy_id,
            emit_holds=self.emit_holds,
        )

    def on_signal(self, action: SignalAction, bar: Bar) -> None:
        print_signal_event(
            action,
            bar,
            mode="live",
            strategy_id=self.strategy_id,
            emit_holds=self.emit_holds,
        )
