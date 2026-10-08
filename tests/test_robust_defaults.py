from __future__ import annotations

import json
from pathlib import Path

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.strategy_defaults import (
    apply_robust_defaults,
    apply_strategy_baseline_defaults,
    best_params_for,
    namespace_for_strategy_backtest,
    robust_params_for,
)
from traderbot.backtesting.robust_defaults import (
    TuneRobustOptions,
    compare_robust_strategies,
    tune_robust_defaults,
    write_robust_defaults_file,
)


def _write_csv(path: Path, closes: list[float]) -> None:
    path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        for index, close in enumerate(closes):
            handle.write(f"{index},{close},{close},{close},{close},1.0\n")


def test_robust_averages_scores_not_params(tmp_path: Path):
    first = tmp_path / "AAA_60.csv"
    second = tmp_path / "BBB_60.csv"
    _write_csv(first, [float(100 + index) for index in range(120)])
    _write_csv(second, [float(200 - index) for index in range(120)])
    payload = tune_robust_defaults(
        TuneRobustOptions(
            csv_paths=[first, second],
            strategy_id="sma_cross",
            param_grid={"fast": [2, 5], "slow": [10, 20]},
            holdout_fraction=0.2,
            min_trades=0,
            min_bars=30,
        ),
        default_strategy_namespace(),
    )
    assert payload["asset_count"] == 2
    assert set(payload["robust_params"]) == {"fast", "slow"}
    # Robust default and single-run best are reported separately.
    assert payload["best_params"] is not None
    assert payload["robust_metrics"]["eligible_assets"] >= 1
    assert len(payload["per_asset_best"]) == 2
    means = {tuple(sorted(row["params"].items())): row["mean_metric"] for row in payload["rows"]}
    robust_key = tuple(sorted(payload["robust_params"].items()))
    assert means[robust_key] == max(means.values())


def test_robust_skips_tiny_csvs(tmp_path: Path):
    tiny = tmp_path / "TINY_60.csv"
    usable = tmp_path / "BIG_60.csv"
    _write_csv(tiny, [100.0] * 10)
    _write_csv(usable, [float(100 + index) for index in range(120)])
    payload = tune_robust_defaults(
        TuneRobustOptions(
            csv_paths=[tiny, usable],
            strategy_id="sma_cross",
            param_grid={"fast": [2, 5], "slow": [10]},
            holdout_fraction=0.2,
            min_trades=0,
            min_bars=30,
        ),
        default_strategy_namespace(),
    )
    assert payload["asset_count"] == 1
    assert payload["skipped_assets"] and payload["skipped_assets"][0]["csv"].endswith("TINY_60.csv")


def test_compare_ranks_strategies_and_defaults_roundtrip(tmp_path: Path):
    first = tmp_path / "AAA_60.csv"
    second = tmp_path / "BBB_60.csv"
    _write_csv(first, [float(100 + index) for index in range(120)])
    _write_csv(second, [float(100 + (index % 10)) for index in range(120)])
    summary = compare_robust_strategies(
        [first, second],
        strategy_ids=["sma_cross", "rsi_threshold"],
        grids_by_strategy={
            "sma_cross": {"fast": [2, 5], "slow": [10]},
            "rsi_threshold": {"period": [7, 14]},
        },
        min_trades=0,
    )
    assert summary["recommended_strategy_id"] in ("sma_cross", "rsi_threshold")
    assert len(summary["ranking"]) == 2

    defaults_path = tmp_path / "strategy_defaults.json"
    write_robust_defaults_file(summary["payloads"], defaults_path)
    loaded_robust = robust_params_for("sma_cross", resolution="60", path=defaults_path)
    loaded_best = best_params_for("sma_cross", resolution="60", path=defaults_path)
    assert loaded_robust is not None and loaded_best is not None
    namespace = default_strategy_namespace()
    applied = apply_robust_defaults(namespace, "sma_cross", resolution="60", path=defaults_path)
    assert applied and namespace.fast == loaded_robust["fast"]
    assert apply_robust_defaults(default_strategy_namespace(), "breakout_atr", resolution="60", path=defaults_path) == []


def test_strategy_baseline_defaults_fix_shared_cli_knobs():
    namespace = default_strategy_namespace()
    apply_strategy_baseline_defaults(namespace, "macd_cross")
    assert namespace.fast == 12 and namespace.slow == 26
    bollinger = default_strategy_namespace()
    apply_strategy_baseline_defaults(bollinger, "bollinger_mean_reversion")
    assert bollinger.period == 20


def test_namespace_for_strategy_backtest_uses_horizon_bucket(tmp_path: Path):
    defaults_path = tmp_path / "strategy_defaults.json"
    defaults_path.write_text(
        json.dumps(
            {
                "horizon:1m": {
                    "sma_cross": {"robust_params": {"fast": 3, "slow": 30}},
                },
                "horizon:1h": {
                    "sma_cross": {"robust_params": {"fast": 7, "slow": 70}},
                },
            }
        ),
        encoding="utf-8",
    )
    csv_1m = tmp_path / "horizons" / "1m" / "BTCIRT_1.csv"
    csv_1h = tmp_path / "horizons" / "1h" / "BTCIRT_60.csv"
    csv_1m.parent.mkdir(parents=True)
    csv_1h.parent.mkdir(parents=True)
    csv_1m.touch()
    csv_1h.touch()

    ns_1m = namespace_for_strategy_backtest("sma_cross", csv_path=csv_1m, defaults_file=defaults_path)
    ns_1h = namespace_for_strategy_backtest("sma_cross", csv_path=csv_1h, defaults_file=defaults_path)
    assert ns_1m.fast == 3 and ns_1m.slow == 30
    assert ns_1h.fast == 7 and ns_1h.slow == 70
