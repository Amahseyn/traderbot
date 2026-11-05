from __future__ import annotations

import math
import numpy as np
import pytest

from traderbot.risk.cointegration_monitor import (
    CointegrationHealthMonitor,
    CointegrationHealthReport,
)


def _generate_cointegrated_series(
    n: int = 150,
    seed: int = 1,
    phi: float = 0.88,
    beta: float = 0.8,
) -> tuple[np.ndarray, np.ndarray, float]:
    np.random.seed(seed)
    trend = np.cumsum(np.random.normal(0, 0.15, n))
    spread = np.zeros(n)
    for i in range(1, n):
        spread[i] = phi * spread[i - 1] + np.random.normal(0, 0.01)

    log_b = 3.0 + trend
    log_a = 4.0 + beta * log_b + spread
    prices_a = np.exp(log_a)
    prices_b = np.exp(log_b)
    spread_std = float(np.std(spread))
    return prices_a, prices_b, spread_std


def test_cointegration_monitor_healthy_pair():
    prices_a, prices_b, spread_std = _generate_cointegrated_series(150, seed=1)
    monitor = CointegrationHealthMonitor(
        max_coint_pvalue=0.10,
        min_beta_stability=0.50,
        max_vol_expansion=2.5,
    )
    report = monitor.evaluate_pair_health(
        prices_a=prices_a,
        prices_b=prices_b,
        hedge_ratio=0.8,
        entry_spread_std=spread_std,
        initial_half_life=4.0,
    )
    assert isinstance(report, CointegrationHealthReport)
    assert report.status == "HEALTHY"
    assert report.recommended_action == "MAINTAIN"
    assert not report.is_broken
    assert len(report.reasons) == 0


def test_cointegration_monitor_breakdown_detection():
    # Start cointegrated, then diverge completely (Asset A keeps rising, Asset B plunges)
    prices_a, prices_b, spread_std = _generate_cointegrated_series(100, seed=1)
    divergence_a = np.linspace(prices_a[-1], prices_a[-1] * 1.5, 50)
    divergence_b = np.linspace(prices_b[-1], prices_b[-1] * 0.5, 50)
    full_a = np.concatenate([prices_a, divergence_a])
    full_b = np.concatenate([prices_b, divergence_b])

    monitor = CointegrationHealthMonitor(max_coint_pvalue=0.05)
    report = monitor.evaluate_pair_health(
        prices_a=full_a,
        prices_b=full_b,
        hedge_ratio=0.8,
        entry_spread_std=spread_std,
        initial_half_life=4.0,
    )
    assert report.is_broken is True
    assert report.status in ("BROKEN", "DEGRADED")
    assert report.recommended_action in ("EMERGENCY_FLATTEN", "SCALE_DOWN")
    assert any("cointegration" in r.lower() or "structural" in r.lower() or "divergence" in r.lower() for r in report.reasons)


def test_cointegration_monitor_volatility_expansion():
    prices_a, prices_b, spread_std = _generate_cointegrated_series(120, seed=1)
    monitor = CointegrationHealthMonitor(max_vol_expansion=2.0)
    # Entry std was tiny (0.0001), current std is much larger
    report = monitor.evaluate_pair_health(
        prices_a=prices_a,
        prices_b=prices_b,
        hedge_ratio=0.8,
        entry_spread_std=0.0001,  # Unrealistically tiny entry std to force expansion
        initial_half_life=4.0,
    )
    assert any("volatility" in r.lower() for r in report.reasons)
    assert report.status in ("DEGRADED", "BROKEN")


def test_cointegration_monitor_half_life_deterioration():
    prices_a, prices_b, spread_std = _generate_cointegrated_series(120, seed=1)
    monitor = CointegrationHealthMonitor(max_half_life_multiple=2.0)
    # Initial half-life was 1 bar; actual half-life of series is ~4 bars -> 4x > 2x limit!
    report = monitor.evaluate_pair_health(
        prices_a=prices_a,
        prices_b=prices_b,
        hedge_ratio=0.8,
        entry_spread_std=spread_std,
        initial_half_life=1.0,
    )
    assert any("half-life" in r.lower() or "half_life" in r.lower() for r in report.reasons)
