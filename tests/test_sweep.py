import pytest

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.backtesting.sweep import SweepOptions, parse_sweep_param, run_strategy_sweep


def _write_csv(path, closes):
    path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        for index, close in enumerate(closes):
            handle.write(f"{index},{close},{close},{close},{close},1.0\n")


def test_parse_sweep_param_typed_values():
    name, values = parse_sweep_param("fast=5,10,20")
    assert name == "fast"
    assert values == [5, 10, 20]
    name, values = parse_sweep_param("oversold=30,25.5")
    assert values == [30, 25.5]
    name, values = parse_sweep_param("price_confirm=true,false")
    assert values == [True, False]


def test_parse_sweep_param_rejects_unknown():
    with pytest.raises(ValueError):
        parse_sweep_param("nope=1,2")
    with pytest.raises(ValueError):
        parse_sweep_param("fast")


def test_sweep_ranks_and_caps_combos(tmp_path):
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [float(100 + index) for index in range(60)])
    options = SweepOptions(
        csv_path=csv_path,
        strategy_id="sma_cross",
        param_grid={"fast": [2, 5], "slow": [10, 20]},
        holdout_tail_bars=10,
    )
    payload = run_strategy_sweep(options, default_strategy_namespace())
    assert payload["combinations"] == 4
    assert payload["rank_by"] == "return_pct"
    assert set(payload["best_params"]) == {"fast", "slow"}
    assert payload["rows"][0]["holdout_return_pct"] is not None

    with pytest.raises(ValueError):
        run_strategy_sweep(
            SweepOptions(
                csv_path=csv_path,
                strategy_id="sma_cross",
                param_grid={"fast": [2, 5], "slow": [10, 20]},
                max_combos=3,
            ),
            default_strategy_namespace(),
        )


def test_sweep_rejects_three_params(tmp_path):
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [100.0] * 40)
    with pytest.raises(ValueError):
        run_strategy_sweep(
            SweepOptions(
                csv_path=csv_path,
                strategy_id="sma_cross",
                param_grid={"fast": [2, 3], "slow": [10, 20], "period": [14, 7]},
            ),
            default_strategy_namespace(),
        )


def test_sweep_skips_invalid_combos(tmp_path):
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [float(100 + index) for index in range(60)])
    payload = run_strategy_sweep(
        SweepOptions(
            csv_path=csv_path,
            strategy_id="sma_cross",
            param_grid={"fast": [5, 50], "slow": [10, 20]},
        ),
        default_strategy_namespace(),
    )
    assert payload["combinations"] + len(payload["skipped"]) == 4
    assert payload["skipped"] and payload["skipped"][0]["params"] == {"fast": 50, "slow": 10}
    assert set(payload["best_params"]) == {"fast", "slow"}


def test_sweep_raises_when_all_combos_invalid(tmp_path):
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [float(100 + index) for index in range(60)])
    with pytest.raises(ValueError, match="no valid combos"):
        run_strategy_sweep(
            SweepOptions(
                csv_path=csv_path,
                strategy_id="sma_cross",
                param_grid={"fast": [50], "slow": [10]},
            ),
            default_strategy_namespace(),
        )


def test_strategy_param_names_follow_registry():
    from traderbot.algorithms.registry import strategy_param_names

    assert strategy_param_names("sma_cross") == ["fast", "slow", "price_confirm"]
    assert strategy_param_names("rsi_threshold") == [
        "period",
        "oversold",
        "overbought",
        "context_bars",
        "buy_min_recent_return",
        "sell_max_recent_return",
        "buy_min_fine_last_5m",
        "sell_max_fine_last_5m",
    ]
    assert strategy_param_names("chart_patterns") == [
        "swing_window_bars",
        "min_swing_separation_bars",
        "pattern_tolerance_ratio",
        "pattern_score_threshold",
    ]
    assert strategy_param_names("breakout_atr") == ["lookback_bars", "atr_period", "atr_multiplier"]
    with pytest.raises(ValueError):
        strategy_param_names("nope")
