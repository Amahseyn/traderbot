from __future__ import annotations

import time
from collections.abc import Iterable

from traderbot.traders.base import Trader


class Bot:
    """Runs one or more traders on a fixed interval."""

    def __init__(self, traders: Iterable[Trader], *, interval_sec = 60.0):
        self.traders = list(traders)
        self.interval_sec = interval_sec

    def run_once(self) -> None:
        for trader in self.traders:
            trader.step()

    def run(self, *, max_steps: int | None = None) -> None:
        steps = 0
        while max_steps is None or steps < max_steps:
            self.run_once()
            steps += 1
            if max_steps is not None and steps >= max_steps:
                break
            time.sleep(self.interval_sec)
