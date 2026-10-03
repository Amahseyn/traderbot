import json
from pathlib import Path

import pytest

from traderbot.algorithms.registry import algorithm_for_id, list_strategies
from traderbot.algorithms.strategies import (
    BollingerMeanReversionAlgorithm,
    EmaCrossAlgorithm,
    MacdCrossAlgorithm,
    RsiThresholdAlgorithm,
    SmaCrossAlgorithm,
)
from traderbot.backtesting import run_backtest
from traderbot.cli.strategy import main as strategy_main


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
    }


def test_algorithm_for_id_sma():
    algo = algorithm_for_id("sma_cross", fast=2, slow=3)
    assert isinstance(algo, SmaCrossAlgorithm)


def test_sma_cross_signals():
    algo = SmaCrossAlgorithm(fast=2, slow=3)
    bars = _bars([1, 2, 3, 2, 1])
    assert algo.on_bar(bars[0]) == "hold"
    assert algo.on_bar(bars[1]) == "hold"
    assert algo.on_bar(bars[2]) == "buy"
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
    # Ramp then dip: fast > slow but close can sit below fast EMA
    closes = [10.0, 10.5, 11.0, 11.5, 12.0, 11.0, 10.5, 10.0]
    actions = [algo.on_bar(b) for b in _bars(closes)]
    plain = EmaCrossAlgorithm(fast=2, slow=4, price_confirm=False)
    plain_actions = [plain.on_bar(b) for b in _bars(closes)]
    assert plain_actions.count("buy") >= actions.count("buy")


def test_strategy_cli_catalog(capsys):
    strategy_main(["catalog", "--implemented"])
    payload = json.loads(capsys.readouterr().out)
    ids = {row["id"] for row in payload}
    assert "sma_cross" in ids


def test_strategy_cli_compare(tmp_path):
    csv_path = tmp_path / "btc.csv"
    closes = [100.0] * 25 + [105.0] * 25
    from traderbot.data.export import write_csv

    write_csv(csv_path, _bars(closes))
    out_dir = tmp_path / "compare_out"
    strategy_main(["compare", str(csv_path), "--out", str(out_dir), "--no-visualize"])
    manifest = json.loads((out_dir / "reports" / "compare_manifest.json").read_text(encoding="utf-8"))
    assert manifest["bars"] == len(closes)
    assert len(manifest["strategies"]) == 5
    assert manifest["best_strategy_id"] in {s["strategy_id"] for s in manifest["strategies"]}
    assert "visualization" not in manifest


def test_strategy_cli_compare_visualization(tmp_path):
    pytest.importorskip("matplotlib")
    csv_path = tmp_path / "btc.csv"
    closes = [100.0] * 30 + [102.0] * 10 + [98.0] * 10 + [104.0] * 20
    from traderbot.data.export import write_csv

    write_csv(csv_path, _bars(closes))
    out_dir = tmp_path / "compare_viz"
    strategy_main(["compare", str(csv_path), "--out", str(out_dir), "--visualize"])
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


def test_strategy_cli_batch_writes_run_tree(tmp_path):
    csv_dir = tmp_path / "ohlc"
    csv_dir.mkdir()
    from traderbot.data.export import write_csv

    write_csv(csv_dir / "btc.csv", _bars([100.0] * 40))
    out = tmp_path / "batch_exp"
    strategy_main(
        [
            "batch",
            str(csv_dir),
            "--strategy",
            "sma_cross",
            "--fast",
            "2",
            "--slow",
            "3",
            "--out",
            str(out),
            "--no-visualize",
        ]
    )
    manifest = json.loads((out / "reports" / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["strategy_id"] == "sma_cross"
    assert len(manifest["runs"]) == 1
    run_dir = Path(manifest["runs"][0]["run_dir"])
    assert run_dir == (out / "runs" / "btc").resolve()
    assert (run_dir / "backtest_summary.json").is_file()


def test_strategy_backtest_visualization(tmp_path):
    pytest.importorskip("matplotlib")
    csv_path = tmp_path / "btc.csv"
    from traderbot.data.export import write_csv

    write_csv(csv_path, _bars([10.0] * 10 + [12.0] * 10))
    out_dir = tmp_path / "single"
    strategy_main(
        ["backtest", str(csv_path), "--strategy", "sma_cross", "--fast", "2", "--slow", "3", "--out", str(out_dir)]
    )
    summary = json.loads((out_dir / "backtest_summary.json").read_text(encoding="utf-8"))
    assert "visualization" in summary
    assert Path(summary["visualization"]["equity_curve"]).is_file()
