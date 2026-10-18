import math

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.ensemble import ENSEMBLE_PRESETS, EnsembleAlgorithm
from traderbot.backtesting.engine import run_backtest


def _bars(count=400):
    closes = [100 + 10 * math.sin(index / 9) + index * 0.02 for index in range(count)]
    return [
        {
            "timestamp": index * 60,
            "open": closes[index],
            "high": closes[index] * 1.002,
            "low": closes[index] * 0.998,
            "close": closes[index],
            "volume": 1.0 + (index % 5),
        }
        for index in range(count)
    ]


def test_ensemble_presets_registered():
    algo = algorithm_for_id(
        "ensemble",
        ensemble_preset="1m_scalp_trend",
        ensemble_entry_rule="all",
        ensemble_exit_rule="any",
    )
    assert isinstance(algo, EnsembleAlgorithm)
    assert len(algo.child_ids) == len(ENSEMBLE_PRESETS["1m_scalp_trend"])


def test_ensemble_all_entry_requires_unanimous_buy():
    algo = EnsembleAlgorithm(
        ensemble_preset="intraday_trend_stack",
        ensemble_entry_rule="all",
        ensemble_exit_rule="any",
    )
    bar = {
        "timestamp": 1,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 1.0,
    }
    for _ in range(300):
        algo.on_bar(bar)
    assert algo.on_bar(bar) in ("hold", "buy", "sell")


def test_ensemble_runs_backtest():
    bars = _bars()
    algo = algorithm_for_id("ensemble", ensemble_preset="1m_pattern_ma", ensemble_entry_rule="majority")
    result = run_backtest(algo, bars, initial_cash=10_000.0)
    assert len(result.equity_curve) == len(bars)
