import json
from pathlib import Path

import pytest

from traderbot.algorithms.cli_args import default_strategy_namespace, merge_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, list_strategies
from traderbot.algorithms.strategies import (
    BollingerMeanReversionAlgorithm,
    EmaCrossAlgorithm,
    MacdCrossAlgorithm,
    RsiThresholdAlgorithm,
    SmaCrossAlgorithm,
)
from traderbot.backtesting import run_backtest
from traderbot.backtesting.batch import StrategyBatchOptions, run_strategy_batch
from traderbot.backtesting.compare_session import StrategyCompareOptions, StrategyTestOptions, run_strategy_compare, run_strategy_test


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": "BTCIRT",
            "resolution": "D",
            "timestamp": i,
            "datetime_utc": "",
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 1.0,
        }
        for i, c in enumerate(closes)
    ]


def test_strategy_catalog_has_implemented_entries():
    implemented = [s for s in list_strategies() if s.implemented]
    assert {s.id for s in implemented} >= {
        "sma_cross",
        "ema_cross",
        "rsi_threshold",
        "macd_cross",
        "bollinger_mean_reversion",
        "chart_patterns",
        "breakout_atr",
    }


def test_algorithm_for_id_sma():
    algo = algorithm_for_id("sma_cross", fast=2, slow=3)
    assert isinstance(algo, SmaCrossAlgorithm)


def test_sma_cross_signals():
    algo = SmaCrossAlgorithm(fast=2, slow=3)
    bars = _bars([1, 2, 3, 2, 1])
    assert algo.on_bar(bars[0]) == "hold"
    assert algo.on_bar(bars[1]) == "hold"
    assert algo.on_bar(bars[2]) == "hold"
    algo.reset()
    for bar in bars[:4]:
        algo.on_bar(bar)
    assert algo.on_bar(bars[4]) == "sell"


def test_ema_cross_runs_backtest():
    closes = [10.0] * 8 + [11.0, 12.0, 13.0, 12.0, 11.0, 10.0]
    result = run_backtest(EmaCrossAlgorithm(fast=2, slow=4), _bars(closes), initial_cash=1000.0)
    assert len(result.equity_curve) == len(closes)
    assert result.final_equity > 0


def test_rsi_threshold_emits_signals_on_swing():
    algo = RsiThresholdAlgorithm(period=3, oversold=40.0, overbought=60.0)
    bars = _bars([100, 99, 98, 97, 96, 97, 98, 99, 100, 101, 102, 103])
    actions = [algo.on_bar(b) for b in bars]
    assert "buy" in actions
    assert "sell" in actions


def test_macd_and_bollinger_instantiate():
    assert MacdCrossAlgorithm(fast=3, slow=5, signal=2).name == "macd_cross"
    assert BollingerMeanReversionAlgorithm(period=5).name == "bollinger_mean_reversion"


def test_bollinger_context_reduces_buys_in_steep_decline():
    closes = [100.0] * 10 + [100.0 - i for i in range(1, 16)]
    bars = _bars(closes)
    plain = BollingerMeanReversionAlgorithm(period=5, num_std=2.0)
    filtered = BollingerMeanReversionAlgorithm(
        period=5,
        num_std=2.0,
        context_bars=3,
        buy_min_recent_return=-0.01,
    )
    plain_buys = sum(1 for b in bars if plain.on_bar(b) == "buy")
    filtered_buys = sum(1 for b in bars if filtered.on_bar(b) == "buy")
    assert plain_buys > 0
    assert filtered_buys < plain_buys


def test_ema_price_confirm_blocks_buy_below_fast():
    algo = EmaCrossAlgorithm(fast=2, slow=4, price_confirm=True)
    closes = [10.0, 10.5, 11.0, 11.5, 12.0, 11.0, 10.5, 10.0]
    actions = [algo.on_bar(b) for b in _bars(closes)]
    plain = EmaCrossAlgorithm(fast=2, slow=4, price_confirm=False)
    plain_actions = [plain.on_bar(b) for b in _bars(closes)]
    assert plain_actions.count("buy") >= actions.count("buy")


def test_strategy_catalog_implemented():
    entries = list_strategies(implemented_only=True)
    ids = {row.id for row in entries}
    assert "sma_cross" in ids


def test_default_strategy_namespace_covers_rule_compare():
    from argparse import Namespace

    from traderbot.algorithms.registry import backtest_strategy_ids, strategy_kwargs_from_namespace

    namespace = default_strategy_namespace()
    for strategy_id in backtest_strategy_ids():
        strategy_kwargs_from_namespace(strategy_id, namespace)

    partial = merge_strategy_namespace(Namespace(fast=5, slow=20, period=14))
    strategy_kwargs_from_namespace("breakout_atr", partial)
    strategy_kwargs_from_namespace("chart_patterns", partial)


def test_strategy_compare_plan_rules_only():
    from traderbot.backtesting.compare_session import strategy_compare_plan

    rules = strategy_compare_plan("strategies")
    assert len(rules) == 7
    assert all(row[0] == row[1] for row in rules)


def test_strategy_compare(tmp_path):
    csv_path = tmp_path / "BTCIRT_60.csv"
    closes = [100.0] * 25 + [105.0] * 25
    from traderbot.data.export import write_csv

    write_csv(csv_path, _bars(closes))
    out_dir = tmp_path / "compare_out"
    run_strategy_compare(
        StrategyCompareOptions(csv_path=csv_path, out_dir=out_dir, visualize=False),
    )
    manifest = json.loads((out_dir / "reports" / "compare_manifest.json").read_text(encoding="utf-8"))
    assert manifest["bars"] == len(closes)
    assert len(manifest["strategies"]) == 7
    assert manifest["best_strategy_id"] in {s["strategy_id"] for s in manifest["strategies"]}
    assert "visualization" not in manifest


def test_strategy_compare_visualization(tmp_path):
    pytest.importorskip("matplotlib")
    csv_path = tmp_path / "BTCIRT_60.csv"
    closes = [100.0] * 30 + [102.0] * 10 + [98.0] * 10 + [104.0] * 20
    from traderbot.data.export import write_csv

    write_csv(csv_path, _bars(closes))
    out_dir = tmp_path / "compare_viz"
    run_strategy_compare(
        StrategyCompareOptions(csv_path=csv_path, out_dir=out_dir, visualize=True),
    )
    manifest = json.loads((out_dir / "reports" / "compare_manifest.json").read_text(encoding="utf-8"))
    viz = manifest["visualization"]
    assert Path(viz["strategy_ranking"]).is_file()
    assert Path(viz["equity_overlay"]).is_file()
    assert Path(viz["drawdown_overlay"]).is_file()
    assert Path(viz["asset_price"]).is_file()
    first_run = out_dir / "runs" / manifest["strategies"][0]["strategy_id"]
    summary = json.loads((first_run / "backtest_summary.json").read_text(encoding="utf-8"))
    per = summary["visualization"]
    assert Path(per["equity_curve"]).is_file()
    assert Path(per["drawdown"]).is_file()
    assert Path(per["price_trades"]).is_file()


def test_strategy_batch_writes_run_tree(tmp_path):
    csv_dir = tmp_path / "ohlc"
    csv_dir.mkdir()
    from traderbot.data.export import write_csv

    write_csv(csv_dir / "BTCIRT_60.csv", _bars([100.0] * 40))
    out = tmp_path / "batch_exp"
    run_strategy_batch(
        StrategyBatchOptions(
            csv_dir=csv_dir,
            strategy_id="sma_cross",
            out_dir=out,
            visualize=False,
            strategy_namespace=default_strategy_namespace(fast=2, slow=3),
        )
    )
    manifest = json.loads((out / "reports" / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["strategy_id"] == "sma_cross"
    assert len(manifest["runs"]) == 1
    run_dir = Path(manifest["runs"][0]["run_dir"])
    assert run_dir == (out / "runs" / "BTCIRT_60").resolve()
    assert (run_dir / "backtest_summary.json").is_file()


def test_strategy_backtest_visualization(tmp_path):
    pytest.importorskip("matplotlib")
    csv_path = tmp_path / "BTCIRT_60.csv"
    from traderbot.data.export import write_csv

    write_csv(csv_path, _bars([10.0] * 10 + [12.0] * 10))
    out_dir = tmp_path / "single"
    summary = run_strategy_test(
        StrategyTestOptions(
            csv_path=csv_path,
            strategy_id="sma_cross",
            out_dir=out_dir,
            visualize=True,
            strategy_namespace=default_strategy_namespace(fast=2, slow=3),
        ),
    )
    assert "run_dir" in summary
    summary_path = Path(summary["run_dir"]) / "backtest_summary.json"
    saved = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "visualization" in saved
    assert Path(saved["visualization"]["equity_curve"]).is_file()
