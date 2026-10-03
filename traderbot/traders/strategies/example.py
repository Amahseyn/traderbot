from __future__ import annotations

from collections.abc import Callable

from traderbot.algorithms.base import Bar
from traderbot.algorithms.registry import algorithm_for_id
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


def sma_trader_from_env(
    *,
    fast = 5,
    slow = 20,
    bar_source: Callable[[], Bar | None] | None = None,
) -> AlgorithmTrader:
    """Live SMA bot template: set ``bar_source`` and subclass :meth:`on_signal` for orders."""
    algo = algorithm_for_id("sma_cross", fast=fast, slow=slow)
    return AlgorithmTrader.from_env(algo, bar_source=bar_source)
