from __future__ import annotations

import math
import pytest

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.walk_forward import (
    PairWalkForwardOptions,
    run_pair_walk_forward,
)


def _make_bar(symbol: str, timestamp: int, price: float) -> dict:
    return {
        "symbol": symbol,
        "resolution": "60",
        "timestamp": timestamp,
        "open": price,
        "high": price * 1.001,
        "low": price * 0.999,
        "close": price,
        "volume": 100.0,
    }


def test_pair_walk_forward_rolling_with_purge_gap():
    """Verify chronological walk-forward with rolling window and purge gap."""
    bar_count = 200
    timestamps = [index * 3600 for index in range(bar_count)]
    dominant_bars = [_make_bar("BTCUSDT", t, 100.0 + (i % 10) * 0.5) for i, t in enumerate(timestamps)]
    hedge_bars = [_make_bar("ETHUSDT", t, 50.0 + (i % 10) * 0.25) for i, t in enumerate(timestamps)]

    options = PairWalkForwardOptions(
        param_grid={
            "entry_threshold": [1.5, 2.0],
            "exit_threshold": [0.4, 0.8],
        },
        dominant_bars=dominant_bars,
        hedge_bars=hedge_bars,
        train_bars=80,
        test_bars=30,
        warmup_bars=20,
        purge_bars=5,
        window_mode="rolling",
    )

    result = run_pair_walk_forward(options)

    assert result["window_mode"] == "rolling"
    assert result["purge_bars"] == 5
    assert len(result["folds"]) >= 2
    for fold in result["folds"]:
        assert "params" in fold
        assert "test_return_pct" in fold
        assert "train_return_pct" in fold
        # Ensure test start is strictly after train_end + purge_bars
        assert fold["test_start"] > fold["train_end"]


def test_pair_walk_forward_expanding_window():
    """Verify chronological walk-forward with expanding window mode."""
    bar_count = 180
    timestamps = [index * 3600 for index in range(bar_count)]
    dominant_bars = [_make_bar("BTCUSDT", t, 100.0 + (i % 8) * 0.4) for i, t in enumerate(timestamps)]
    hedge_bars = [_make_bar("ETHUSDT", t, 50.0 + (i % 8) * 0.2) for i, t in enumerate(timestamps)]

    options = PairWalkForwardOptions(
        param_grid={
            "entry_threshold": [1.5, 2.0],
        },
        dominant_bars=dominant_bars,
        hedge_bars=hedge_bars,
        train_bars=60,
        test_bars=30,
        warmup_bars=15,
        purge_bars=0,
        window_mode="expanding",
    )

    result = run_pair_walk_forward(options)
    assert result["window_mode"] == "expanding"
    assert len(result["folds"]) >= 2
    # In expanding window, each subsequent fold has a larger training duration
    train_bars_fold1 = result["folds"][0]["train_bars"]
    train_bars_fold2 = result["folds"][1]["train_bars"]
    assert train_bars_fold2 > train_bars_fold1
    assert "parameter_stability" in result

