from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable

from traderbot.traders.base import Trader

logger = logging.getLogger(__name__)

STOP_CHECK_SECONDS = 0.25


class Bot:
    """Runs one or more traders on a fixed interval."""

    def __init__(self, traders: Iterable[Trader], *, interval_sec = 60.0):
        self.traders = list(traders)
        self.interval_sec = interval_sec

    def run_once(self) -> None:
        for trader in self.traders:
            try:
                trader.step()
            except Exception:
                logger.exception("trader step failed for %s", getattr(trader, "name", trader))

    def run(
        self,
        *,
        max_steps: int | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        steps = 0
        while max_steps is None or steps < max_steps:
            if should_stop is not None and should_stop():
                break
            self.run_once()
            steps += 1
            if max_steps is not None and steps >= max_steps:
                break
            if should_stop is not None and should_stop():
                break
            if self._sleep_until_stop(self.interval_sec, should_stop):
                break

    def _sleep_until_stop(
        self,
        seconds: float,
        should_stop: Callable[[], bool] | None,
    ) -> bool:
        deadline = time.monotonic() + seconds
        while True:
            if should_stop is not None and should_stop():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(STOP_CHECK_SECONDS, remaining))
