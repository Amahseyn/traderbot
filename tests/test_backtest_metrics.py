from __future__ import annotations

import math
import pytest

from traderbot.backtesting.metrics import (
    annualized_sharpe_ratio,
    annualized_sortino_ratio,
    calmar_ratio,
    expectancy,
    exposure_time_pct,
    pair_buy_and_hold_benchmarks,
    profit_factor,
    turnover_ratio,
)


def test_sharpe_sortino_calculations():
    # Regular positive returns with some variance
    returns = [0.01, -0.005, 0.02, -0.008, 0.015, -0.002, 0.012, 0.005]
    sharpe = annualized_sharpe_ratio(returns, periods_per_year=365)
    sortino = annualized_sortino_ratio(returns, periods_per_year=365)

    assert sharpe is not None and sharpe > 0
    assert sortino is not None and sortino > 0
    # Downside std is typically <= total std for positively skewed returns, so Sortino >= Sharpe
    assert sortino >= sharpe


def test_profit_factor_and_expectancy():
    pnls = [100.0, -50.0, 200.0, -50.0, 150.0]
    # Total wins: 100 + 200 + 150 = 450
    # Total losses: 50 + 50 = 100
    # Profit factor: 450 / 100 = 4.5
    # Expectancy: (450 - 100) / 5 = 70.0
    pf = profit_factor(pnls)
    exp = expectancy(pnls)

    assert math.isclose(pf, 4.5, rel_tol=1e-5)
    assert math.isclose(exp, 70.0, rel_tol=1e-5)


def test_calmar_and_exposure_metrics():
    cagr = 25.0
    max_dd = -10.0
    calmar = calmar_ratio(cagr, max_dd)
    assert math.isclose(calmar, 2.5, rel_tol=1e-5)

    # Exposure curve: 10 bars total, 6 with non-zero exposure -> 60%
    exposure_curve = [(t, 100.0 if i < 6 else 0.0) for i, t in enumerate(range(10))]
    exp_time = exposure_time_pct(exposure_curve)
    assert math.isclose(exp_time, 60.0, rel_tol=1e-5)


def test_pair_buy_and_hold_benchmarks():
    bars_a = [{"timestamp": 0, "close": 100.0}, {"timestamp": 3600, "close": 120.0}]  # +20%
    bars_b = [{"timestamp": 0, "close": 50.0}, {"timestamp": 3600, "close": 40.0}]    # -20%

    benchmarks = pair_buy_and_hold_benchmarks(bars_a, bars_b, initial_cash=10_000.0)
    assert math.isclose(benchmarks["buy_hold_a_pct"], 20.0, rel_tol=1e-5)
    assert math.isclose(benchmarks["buy_hold_b_pct"], -20.0, rel_tol=1e-5)
    assert math.isclose(benchmarks["equal_weight_pct"], 0.0, rel_tol=1e-5)

