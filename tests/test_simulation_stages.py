import math

from traderbot.ml.simulation_config import SimulationConfig, simulation_config_from_horizon
from traderbot.ml.simulator import simulate_holdout_account


def _series(closes: list[float], *, bar_sec = 3600) -> list[tuple[int, float]]:
    t0 = 1_700_000_000
    return [(t0 + i * bar_sec, c) for i, c in enumerate(closes)]


def test_sim_align_to_horizon_reduces_steps():
    bar_sec = 3600
    horizon = 4
    prices = _series([100.0] * 20, bar_sec=bar_sec)
    t0 = prices[0][0]
    ts = [t0 + i * bar_sec for i in range(8)]
    y_true = [0.05] * 8
    y_pred = [-1.0] * 8

    default = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
    )
    aligned = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
        sim_config=simulation_config_from_horizon(
            horizon_bars=horizon,
            bar_minutes=60,
            sim_align_to_horizon=True,
        ),
    )
    assert default.metrics["simulation_steps"] > aligned.metrics["simulation_steps"]


def test_sim_decision_bars_when_flat():
    bar_sec = 3600
    horizon = 2
    prices = _series([100.0] * 12, bar_sec=bar_sec)
    t0 = prices[0][0]
    ts = [t0 + i * bar_sec for i in range(6)]
    y_true = [0.0] * 6
    y_pred = [-1.0] * 6

    step1 = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
        sim_config=SimulationConfig(horizon_bars=horizon, bar_minutes=60, decision_bars=1),
    )
    step2 = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
        sim_config=SimulationConfig(horizon_bars=horizon, bar_minutes=60, decision_bars=2),
    )
    assert step1.metrics["simulation_steps"] > step2.metrics["simulation_steps"]


def test_sim_hold_bars_independent_of_horizon_pnl():
    bar_sec = 3600
    horizon = 4
    prices = _series([100.0] * 16, bar_sec=bar_sec)
    t0 = prices[0][0]
    ts = [t0 + i * bar_sec for i in range(8)]
    y_true = [0.10] * 8
    y_pred = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

    out = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
        sim_config=SimulationConfig(horizon_bars=horizon, bar_minutes=60, hold_bars=2),
    )
    expected = 100.0 * math.exp(0.40)
    assert out.metrics["strategy_trades"] == 4.0
    assert abs(out.metrics["strategy_final_usd"] - expected) < 0.05
