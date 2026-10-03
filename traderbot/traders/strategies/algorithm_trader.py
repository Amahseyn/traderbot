from __future__ import annotations

from collections.abc import Callable

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.nobitex.client import NobitexClient
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.nobitex import NobitexTrader

BarSource = Callable[[], Bar | None]


class AlgorithmTrader(NobitexTrader):
    """
    Runs an :class:`~traderbot.algorithms.base.Algorithm` each ``step``.

    Provide ``bar_source`` (latest candle) and override :meth:`on_signal` for order placement.
    Backtests use the same algorithm class via :func:`traderbot.backtesting.run_backtest`.
    """

    name = "algorithm"

    def __init__(
        self,
        client,
        algorithm: Algorithm,
        *,
        bar_source: BarSource | None = None,
        execution: ExecutionPolicy | None = None,
    ):
        super().__init__(client)
        self.algorithm = algorithm
        self.bar_source = bar_source
        self.execution = execution or ExecutionPolicy.paper_only()
        self.algorithm.reset()

    @classmethod
    def from_env(
        cls,
        algorithm: Algorithm,
        *,
        bar_source: BarSource | None = None,
        execution: ExecutionPolicy | None = None,
    ) -> AlgorithmTrader:
        return cls(
            NobitexClient.from_env(),
            algorithm,
            bar_source=bar_source,
            execution=execution,
        )

    def step(self) -> None:
        bar = self.bar_source() if self.bar_source else None
        if bar is None:
            return
        action = self.algorithm.on_bar(bar)
        if not self.execution.permits(action):
            return
        if self.execution.mode == "paper":
            self.on_paper_signal(action, bar)
        else:
            self.on_signal(action, bar)

    def on_paper_signal(self, action: SignalAction, bar: Bar) -> None:
        """Hook for logging or sim fills when :attr:`execution` is paper mode."""

    def on_signal(self, action: SignalAction, bar: Bar) -> None:
        """Hook: map buy/sell to Nobitex API calls in your subclass (live mode only by default)."""
