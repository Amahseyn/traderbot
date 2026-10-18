from __future__ import annotations

import pytest

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.backtesting.optimize_select import OptimizeSelectConfig, run_strategy_optimize
from traderbot.backtesting.sweep import SweepOptions
from traderbot.backtesting.tune_search_space import resolve_tune_param_names, suggest_strategy_params


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


def test_resolve_tune_param_names_defaults_to_all_strategy_params() -> None:
    names = resolve_tune_param_names("sma_cross")
    assert set(names) == {"fast", "slow", "price_confirm"}


def test_suggest_strategy_params_respects_fast_lt_slow() -> None:
    optuna = pytest.importorskip("optuna")

    class _Trial:
        def __init__(self) -> None:
            self._index = 0

        def suggest_categorical(self, name: str, choices: list) -> object:
            if name == "fast":
                return 20
            if name == "slow":
                return 10
            return choices[0]

        def suggest_int(self, name: str, low: int, high: int) -> int:
            return low

        def suggest_float(self, name: str, low: float, high: float) -> float:
            return low

    with pytest.raises(ValueError, match="fast must be < slow"):
        suggest_strategy_params(_Trial(), "sma_cross", ["fast", "slow"])


def test_run_strategy_optuna_optimize_validation_shape() -> None:
    pytest.importorskip("optuna")
    closes = [100.0 + index * 0.2 for index in range(120)]
    payload = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [5], "slow": [20]},
            bars=_bars(closes),
            min_trades=0,
        ),
        default_strategy_namespace(),
        config=OptimizeSelectConfig(
            selection_mode="validation",
            optimizer_method="optuna",
            n_trials=12,
            search_params=("fast", "slow"),
        ),
    )
    assert payload["optimizer_method"] == "optuna"
    assert payload["best_params"]
    assert payload["optuna"]["n_trials"] >= 1
    assert set(payload["best_params"]) <= {"fast", "slow", "price_confirm"}
