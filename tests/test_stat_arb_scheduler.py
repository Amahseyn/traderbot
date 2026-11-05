from __future__ import annotations

import pytest

from traderbot.analysis.pairs.scheduler import (
    StatArbScheduleConfig,
    StatArbScheduler,
)


def test_independent_schedule_intervals_and_caching():
    """Verify independent configurable schedule intervals and execution triggers."""
    config = StatArbScheduleConfig(
        universe_interval_sec=100.0,
        ohlcv_interval_sec=20.0,
        correlation_interval_sec=60.0,
        cointegration_interval_sec=80.0,
        pair_ranking_interval_sec=40.0,
        strategy_eval_interval_sec=10.0,
        risk_monitor_interval_sec=5.0,
        min_new_bars_for_coint=3,
    )
    scheduler = StatArbScheduler(config=config, start_time=1000.0)

    # At start (t = 1000.0), all tasks are due
    assert scheduler.is_task_due("universe", now=1000.0)
    assert scheduler.is_task_due("ohlcv", now=1000.0)
    assert scheduler.is_task_due("correlation", now=1000.0)
    assert scheduler.is_task_due("cointegration", now=1000.0)
    assert scheduler.is_task_due("pair_ranking", now=1000.0)
    assert scheduler.is_task_due("strategy_eval", now=1000.0)
    assert scheduler.is_task_due("risk_monitor", now=1000.0)

    # Mark all completed at t = 1000.0
    for task in ["universe", "ohlcv", "correlation", "cointegration", "pair_ranking", "strategy_eval", "risk_monitor"]:
        scheduler.mark_task_completed(task, now=1000.0)

    # At t = 1004.0: none due
    assert not scheduler.is_task_due("risk_monitor", now=1004.0)
    assert scheduler.get_next_sleep_seconds(now=1004.0) == pytest.approx(1.0)

    # At t = 1005.0: only risk_monitor due
    assert scheduler.is_task_due("risk_monitor", now=1005.0)
    assert not scheduler.is_task_due("strategy_eval", now=1005.0)

    # At t = 1010.0: strategy_eval due, but not ohlcv or correlation
    assert scheduler.is_task_due("strategy_eval", now=1010.0)
    assert not scheduler.is_task_due("ohlcv", now=1010.0)
    assert not scheduler.is_task_due("correlation", now=1010.0)

    # At t = 1025.0: ohlcv due (interval 20)
    assert scheduler.is_task_due("ohlcv", now=1025.0)

    # Test caching predicates:
    # 1. Bar update cache
    scheduler.update_bar_cache_timestamp("BTC", 1000)
    assert not scheduler.should_download_bars("BTC", latest_known_timestamp=1000)
    assert scheduler.should_download_bars("BTC", latest_known_timestamp=1060)

    # 2. Cointegration re-scan gating
    assert not scheduler.should_rescan_cointegration(accumulated_new_bars=2)
    assert scheduler.should_rescan_cointegration(accumulated_new_bars=3)


def test_scheduler_step_execution():
    """Verify execution of registered callbacks during step()."""
    config = StatArbScheduleConfig(
        universe_interval_sec=100.0,
        risk_monitor_interval_sec=5.0,
        strategy_eval_interval_sec=10.0,
    )
    executed = []

    def mock_risk():
        executed.append("risk")

    def mock_strategy():
        executed.append("strategy")

    scheduler = StatArbScheduler(config=config, start_time=1000.0)
    scheduler.register_handler("risk_monitor", mock_risk)
    scheduler.register_handler("strategy_eval", mock_strategy)

    # At start, both execute
    scheduler.step(now=1000.0)
    assert "risk" in executed
    assert "strategy" in executed

    # Step at t = 1006.0: only risk should fire again
    executed.clear()
    scheduler.step(now=1006.0)
    assert executed == ["risk"]

    # Step at t = 1011.0: both fire
    executed.clear()
    scheduler.step(now=1011.0)
    assert "risk" in executed
    assert "strategy" in executed

