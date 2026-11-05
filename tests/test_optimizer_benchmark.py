from __future__ import annotations

import pytest

from traderbot.analysis.optimizer_benchmark import (
    compute_overfitting_index,
    run_single_shootout_cell,
)


def _synthetic_bars(count: int = 120) -> list[dict]:
    # Creates oscillatory bars with slight trend
    bars = []
    price = 100.0
    for i in range(count):
        price += (i % 7 - 3) * 0.5 + (0.05 if i % 2 == 0 else -0.04)
        bars.append(
            {
                "timestamp": 1700000000 + i * 3600,
                "open": round(price - 0.2, 2),
                "high": round(price + 0.8, 2),
                "low": round(price - 0.8, 2),
                "close": round(price, 2),
                "volume": 100.0 + (i % 10) * 10,
            }
        )
    return bars


def test_compute_overfitting_index() -> None:
    # High train return, negative test return -> high overfitting index
    index = compute_overfitting_index(10.0, -2.0)
    assert index == 1.2

    # Equal train and test -> 0.0 overfitting
    index = compute_overfitting_index(5.0, 5.0)
    assert index == 0.0

    # Test outperforms train -> negative overfitting
    index = compute_overfitting_index(2.0, 4.0)
    assert index == -1.0


def test_run_single_shootout_cell_grid() -> None:
    bars = _synthetic_bars(100)
    result = run_single_shootout_cell(
        strategy_id="bollinger_mean_reversion",
        bars=bars,
        method="grid",
        selection_mode="validation",
        optuna_trials=5,
        resolution="60",
    )
    assert result["strategy_id"] == "bollinger_mean_reversion"
    assert result["method"] == "grid"
    assert result["selection_mode"] == "validation"
    assert "test_return_pct" in result
    assert "overfitting_index" in result
    assert "elapsed_seconds" in result


def test_run_single_shootout_cell_optuna_tpe() -> None:
    pytest.importorskip("optuna")
    bars = _synthetic_bars(100)
    result = run_single_shootout_cell(
        strategy_id="ema_cross",
        bars=bars,
        method="optuna_tpe",
        selection_mode="in_sample",
        optuna_trials=6,
        resolution="60",
    )
    assert result["strategy_id"] == "ema_cross"
    assert result["method"] == "optuna_tpe"
    assert result["selection_mode"] == "in_sample"
    assert "test_return_pct" in result
    assert "overfitting_index" in result

