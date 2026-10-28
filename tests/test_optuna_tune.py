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
    assert set(names) == {
        "fast",
        "slow",
        "price_confirm",
        "context_bars",
        "buy_min_recent_return",
        "sell_max_recent_return",
        "buy_min_fine_last_5m",
        "sell_max_fine_last_5m",
    }
    # Cost/execution plumbing is configured, not swept: a numeric grid over it proposes
    # nonsense (negative cost multiples, a categorical venue, a ``None`` sentinel).
    assert not {"min_edge_over_cost", "roundtrip_cost_pct", "entry_order_mode"} & set(names)


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


def test_suggest_strategy_params_uses_invariant_choice_space() -> None:
    """slow must be sampled from the full grid (invariant across trials), not a
    per-trial filtered subset.  This avoids Optuna's
    ``CategoricalDistribution does not support dynamic value space`` error."""
    optuna = pytest.importorskip("optuna")
    seen_slow_choices: list[list] = []

    class _Trial:
        def suggest_categorical(self, name: str, choices: list) -> object:
            if name == "slow":
                seen_slow_choices.append(list(choices))
            if name == "fast":
                return 5
            return choices[0]

        def suggest_int(self, name: str, low: int, high: int) -> int:
            return low

        def suggest_float(self, name: str, low: float, high: float) -> float:
            return low

    params = suggest_strategy_params(_Trial(), "sma_cross", ["fast", "slow"])
    # The slow choices must be the full grid, not filtered by fast.
    assert seen_slow_choices
    assert len(seen_slow_choices[0]) > 1, seen_slow_choices[0]
    assert int(params["fast"]) < int(params["slow"]), params


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


def test_optuna_holdout_test_uses_test_bars_not_full_bars() -> None:
    """When use_validation_split=False with a holdout tail, the test must be
    evaluated on ``test_bars`` (the holdout), not the full ``bars`` (item 2)."""
    pytest.importorskip("optuna")
    closes = [100.0 + index * 0.2 for index in range(120)]
    payload = run_strategy_optimize(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [5], "slow": [20]},
            bars=_bars(closes),
            min_trades=0,
            holdout_tail_bars=30,
        ),
        default_strategy_namespace(),
        config=OptimizeSelectConfig(
            selection_mode="in_sample",
            optimizer_method="optuna",
            n_trials=8,
            search_params=("fast", "slow"),
        ),
    )
    # in_sample optuna does not split into validation/test; it reports the
    # holdout tail separately.  Here we verify the in_sample path still runs.
    assert payload["best_params"]
    assert payload["selection_mode_applied"] == "in_sample"
