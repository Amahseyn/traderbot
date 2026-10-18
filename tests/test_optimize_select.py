from __future__ import annotations

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.backtesting.optimize_select import (
    MIN_BARS_FOR_VALIDATION_SPLIT,
    OptimizeSelectConfig,
    run_strategy_optimize,
)
from traderbot.backtesting.sweep import SweepOptions


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "timestamp": index * 60,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        }
        for index, close in enumerate(closes)
    ]


def test_validation_mode_produces_sweep_shape() -> None:
    closes = [100.0 + index for index in range(120)]
    payload = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [3, 8], "slow": [12, 20]},
            bars=_bars(closes),
            min_trades=0,
        ),
        default_strategy_namespace(),
        config=OptimizeSelectConfig(selection_mode="validation"),
    )
    assert payload["selection_mode_applied"] == "validation"
    assert payload["best_params"]
    # Default ranking is edge (significance, then net avg per trade); return_pct stays available.
    assert payload["rank_by"] == "validation_edge"
    assert payload.get("test") is not None
    assert payload.get("splits")


def test_short_history_falls_back_to_in_sample() -> None:
    bar_count = MIN_BARS_FOR_VALIDATION_SPLIT - 5
    closes = [100.0 + index * 0.1 for index in range(bar_count)]
    payload = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [3, 8], "slow": [12, 20]},
            bars=_bars(closes),
            min_trades=0,
        ),
        default_strategy_namespace(),
        config=OptimizeSelectConfig(selection_mode="validation"),
    )
    assert payload["selection_mode_applied"] == "in_sample_fallback"
    assert payload["best_params"]


def test_in_sample_explicit_mode() -> None:
    closes = [100.0 + index for index in range(80)]
    payload = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [3, 8], "slow": [12, 20]},
            bars=_bars(closes),
            min_trades=0,
            holdout_tail_bars=10,
        ),
        default_strategy_namespace(),
        config=OptimizeSelectConfig(selection_mode="in_sample"),
    )
    assert payload["selection_mode_applied"] == "in_sample"
    assert payload["rank_by"] == "edge"


def test_optimize_winner_depends_on_price_series() -> None:
    """Grid optimize is per bar series — different markets/CSV data can pick different params."""
    trending = [100.0 + index * 0.5 for index in range(120)]
    oscillating = [100.0 + (5.0 if index % 10 < 5 else -5.0) for index in range(120)]
    grid = {"fast": [3, 8], "slow": [12, 20]}
    config = OptimizeSelectConfig(selection_mode="validation")
    first = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid=grid,
            bars=_bars(trending),
            min_trades=0,
        ),
        default_strategy_namespace(),
        config=config,
    )
    second = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid=grid,
            bars=_bars(oscillating),
            min_trades=0,
        ),
        default_strategy_namespace(),
        config=config,
    )
    assert first["best_params"] != second["best_params"]
