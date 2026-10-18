from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable

from traderbot.traders.base import Trader

logger = logging.getLogger(__name__)

STOP_CHECK_SECONDS = 0.25


#: After a bar boundary, re-poll this often until the new bar shows up (API publish lag).
BAR_RETRY_SECONDS = 2.0
BAR_RETRY_WINDOW_SECONDS = 20.0


class Bot:
    """Runs one or more traders on an interval.

    With ``bar_seconds`` the loop wakes ``close_delay_sec`` after each bar close instead of on a
    free-running timer (never later than ``interval_sec``), retries briefly until the new bar is
    published, and steps again immediately while a bar source still has queued (missed) bars.
    """

    def __init__(
        self,
        traders: Iterable[Trader],
        *,
        interval_sec = 60.0,
        bar_seconds: float | None = None,
        close_delay_sec: float = 1.0,
        clock: Callable[[], float] = time.time,
    ):
        self.traders = list(traders)
        self.interval_sec = interval_sec
        self.bar_seconds = bar_seconds
        self.close_delay_sec = close_delay_sec
        self._clock = clock

    def _pending_bars(self) -> int:
        total = 0
        for trader in self.traders:
            pending = getattr(getattr(trader, "bar_source", None), "pending", None)
            if callable(pending):
                try:
                    total += int(pending())
                except Exception:
                    pass
        return total

    def _got_bar(self) -> bool:
        return any(getattr(trader, "last_step_got_bar", True) for trader in self.traders)

    def next_sleep_seconds(self) -> float:
        if self._pending_bars() > 0:
            return 0.0
        if not self.bar_seconds:
            return float(self.interval_sec)
        now = self._clock()
        bar = float(self.bar_seconds)
        since_close = (now - self.close_delay_sec) % bar
        if not self._got_bar() and since_close < BAR_RETRY_WINDOW_SECONDS:
            return min(float(self.interval_sec), BAR_RETRY_SECONDS)
        return max(0.0, min(float(self.interval_sec), bar - since_close))

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
            if self._sleep_until_stop(self.next_sleep_seconds(), should_stop):
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
