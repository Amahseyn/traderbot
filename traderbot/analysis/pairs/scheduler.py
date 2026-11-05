from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StatArbScheduleConfig:
    """Configurable execution intervals for statistical arbitrage operations."""

    universe_interval_sec: float = 86_400.0  # 24h
    ohlcv_interval_sec: float = 300.0  # 5m
    correlation_interval_sec: float = 3_600.0  # 1h
    cointegration_interval_sec: float = 7_200.0  # 2h
    pair_ranking_interval_sec: float = 3_600.0  # 1h
    strategy_eval_interval_sec: float = 60.0  # 1m
    risk_monitor_interval_sec: float = 15.0  # 15s
    min_new_bars_for_coint: int = 5  # Minimum new bars before recomputing regressions


class StatArbScheduler:
    """
    Decoupled multi-interval scheduler with caching guards to avoid unnecessary
    network requests and expensive statistical recalculations.
    """

    def __init__(
        self,
        config: StatArbScheduleConfig | None = None,
        *,
        start_time: float | None = None,
    ) -> None:
        self.config = config or StatArbScheduleConfig()
        self.start_time = start_time if start_time is not None else time.time()
        # Initialize last run timestamps so all tasks are due initially
        self.last_run_timestamps: dict[str, float] = {}
        self.handlers: dict[str, Callable[[], Any]] = {}
        self.bar_cache_timestamps: dict[str, int] = {}

    def _get_interval(self, task_name: str) -> float:
        task = task_name.lower()
        if task in ("universe", "market_universe"):
            return self.config.universe_interval_sec
        if task in ("ohlcv", "bars"):
            return self.config.ohlcv_interval_sec
        if task in ("correlation", "corr"):
            return self.config.correlation_interval_sec
        if task in ("cointegration", "coint"):
            return self.config.cointegration_interval_sec
        if task in ("pair_ranking", "ranking"):
            return self.config.pair_ranking_interval_sec
        if task in ("strategy_eval", "strategy", "signals"):
            return self.config.strategy_eval_interval_sec
        if task in ("risk_monitor", "risk"):
            return self.config.risk_monitor_interval_sec
        return 60.0

    def is_task_due(self, task_name: str, now: float | None = None) -> bool:
        """Check if a specific task interval has elapsed."""
        current_time = now if now is not None else time.time()
        last = self.last_run_timestamps.get(task_name)
        if last is None:
            return True
        interval = self._get_interval(task_name)
        return (current_time - last) >= interval

    def mark_task_completed(self, task_name: str, now: float | None = None) -> None:
        """Mark task as successfully executed at instant `now`."""
        current_time = now if now is not None else time.time()
        self.last_run_timestamps[task_name] = current_time

    def get_next_sleep_seconds(self, now: float | None = None) -> float:
        """Calculate minimum seconds to wait until any task is due."""
        current_time = now if now is not None else time.time()
        all_tasks = [
            "universe",
            "ohlcv",
            "correlation",
            "cointegration",
            "pair_ranking",
            "strategy_eval",
            "risk_monitor",
        ]
        time_to_next: list[float] = []
        for task in all_tasks:
            last = self.last_run_timestamps.get(task)
            if last is None:
                return 0.0
            interval = self._get_interval(task)
            elapsed = current_time - last
            remaining = max(0.0, interval - elapsed)
            time_to_next.append(remaining)

        return min(time_to_next) if time_to_next else 0.0

    def update_bar_cache_timestamp(self, symbol: str, timestamp: int) -> None:
        """Record latest known bar timestamp for caching checks."""
        self.bar_cache_timestamps[symbol.upper()] = timestamp

    def should_download_bars(self, symbol: str, latest_known_timestamp: int) -> bool:
        """Predicate to check if remote bar fetching is needed."""
        cached_ts = self.bar_cache_timestamps.get(symbol.upper())
        if cached_ts is None:
            return True
        return latest_known_timestamp > cached_ts

    def should_rescan_cointegration(self, accumulated_new_bars: int) -> bool:
        """Predicate to check if sufficient new bars exist to justify re-running OLS regressions."""
        return accumulated_new_bars >= self.config.min_new_bars_for_coint

    def register_handler(self, task_name: str, handler: Callable[[], Any]) -> None:
        """Register executable callable for a task interval."""
        self.handlers[task_name] = handler

    def step(self, now: float | None = None) -> dict[str, Any]:
        """Execute all due task handlers and return execution summary."""
        current_time = now if now is not None else time.time()
        executed_tasks: dict[str, Any] = {}

        for task_name, handler in self.handlers.items():
            if self.is_task_due(task_name, now=current_time):
                try:
                    result = handler()
                    self.mark_task_completed(task_name, now=current_time)
                    executed_tasks[task_name] = {"status": "ok", "result": result}
                except Exception as exc:
                    logger.exception("Error executing scheduled task %s: %s", task_name, exc)
                    executed_tasks[task_name] = {"status": "error", "error": str(exc)}

        return executed_tasks

    def run(
        self,
        *,
        max_steps: int | None = None,
        should_stop: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Run continuous scheduler loop respecting stop signal and step bounds."""
        steps = 0
        while max_steps is None or steps < max_steps:
            if should_stop is not None and should_stop():
                break
            now = clock()
            self.step(now=now)
            steps += 1
            if max_steps is not None and steps >= max_steps:
                break
            if should_stop is not None and should_stop():
                break
            sleep_sec = self.get_next_sleep_seconds(now=clock())
            if sleep_sec > 0:
                sleep_fn(min(sleep_sec, 1.0))

