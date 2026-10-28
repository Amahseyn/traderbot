from traderbot.algorithms.registry import implemented_strategy_ids
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
        "spot_grid",
        "pair_trading",
        "funding_carry",
        "perp_market_making",
        "ma_trend",
        "grid",
        "dca",
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


def _micro_noise_closes(*, bars: int = 240, seed: int = 7, step_pct: float = 0.0002) -> list[float]:
    """A random walk whose per-bar drift is far inside a 0.19% roundtrip."""
    import random

    rng = random.Random(seed)
    price = 100.0
    closes = []
    for _ in range(bars):
        price *= 1.0 + rng.uniform(-step_pct, step_pct)
        closes.append(price)
    return closes


def test_cost_gate_cuts_one_minute_whipsaw_trades():
    """The whole point: a 0.19% roundtrip must not be paid for a 0.02% drift."""
    closes = _micro_noise_closes()
    bars = _bars(closes)
    ungated = MacdCrossAlgorithm(fast=12, slow=26, min_edge_over_cost=0.0)
    gated = MacdCrossAlgorithm(fast=12, slow=26, min_edge_over_cost=1.0)
    ungated_buys = sum(1 for bar in bars if ungated.on_bar(bar) == "buy")
    gated_buys = sum(1 for bar in bars if gated.on_bar(bar) == "buy")
    assert ungated_buys > 0
    assert gated_buys < ungated_buys


def test_cost_gate_keeps_moves_that_clear_the_roundtrip():
    """A trend that clears the friction still trades — the gate is not a mute button."""
    closes = [100.0] * 30 + [100.0 * (1.005**step) for step in range(1, 31)]
    gated = SmaCrossAlgorithm(fast=5, slow=20, min_edge_over_cost=1.0)
    actions = [gated.on_bar(bar) for bar in _bars(closes)]
    assert "buy" in actions
    ungated = SmaCrossAlgorithm(fast=5, slow=20, min_edge_over_cost=0.0)
    ungated_actions = [ungated.on_bar(bar) for bar in _bars(closes)]
    assert ungated_actions.count("buy") >= actions.count("buy")


def test_cost_gate_off_by_default_on_direct_construction():
    # The backtest namespace resolves the gate from the bar size; a bare instance is legacy.
    assert SmaCrossAlgorithm(fast=5, slow=20).min_edge_over_cost == 0.0
    assert BollingerMeanReversionAlgorithm(period=20).min_edge_over_cost == 0.0
    assert MacdCrossAlgorithm().min_edge_over_cost == 0.0
    assert RsiThresholdAlgorithm().min_edge_over_cost == 0.0
    assert EmaCrossAlgorithm().min_edge_over_cost == 0.0


def test_cost_gate_uses_the_venue_roundtrip_when_given():
    """Nobitex's 0.90% roundtrip must reject moves Hyperliquid's 0.19% would accept."""
    closes = [100.0, 99.9, 99.8, 99.7, 99.6, 99.5, 99.4, 99.3, 99.2, 99.1, 99.0] * 3
    cheap = RsiThresholdAlgorithm(
        period=3,
        oversold=45.0,
        min_edge_over_cost=1.0,
        roundtrip_cost_pct=0.0019,
    )
    dear = RsiThresholdAlgorithm(
        period=3,
        oversold=45.0,
        min_edge_over_cost=1.0,
        roundtrip_cost_pct=0.009,
    )
    bars = _bars(closes)
    assert sum(1 for bar in bars if cheap.on_bar(bar) == "buy") >= sum(
        1 for bar in bars if dear.on_bar(bar) == "buy"
    )


def test_maker_entry_rests_a_post_only_limit_below_the_close():
    from traderbot.algorithms.entry_orders import MakerEntry

    entry = MakerEntry(entry_order_mode="maker", entry_offset_pct=0.0002, entry_ttl_bars=3)
    assert entry.limit_price("buy", 100.0) == pytest.approx(100.0 * (1 - 0.0002))
    # A sell would rest above the close so it never crosses into a taker fill.
    assert entry.limit_price("sell", 100.0) == pytest.approx(100.0 * (1 + 0.0002))
    spec = entry.spec_for("buy", 100.0)
    assert spec is not None and spec.post_only is True and spec.ttl_bars == 3
    assert entry.spec_for("hold", 100.0) is None
    # Sells close risk: an exit that never fills is worse than the fee it saves.
    assert entry.spec_for("sell", 100.0) is None
    assert MakerEntry().spec_for("buy", 100.0) is None  # market mode keeps the default fill


def test_maker_entry_signal_exposes_a_limit_spec_for_the_signal_bar():
    algo = SmaCrossAlgorithm(fast=2, slow=4, entry_order_mode="maker", entry_offset_pct=0.0002)
    assert algo.uses_order_engine is True
    assert algo.entry_order_mode == "maker"
    specs = []
    for bar in _bars([10.0, 10.0, 10.0, 10.0, 11.0, 12.0, 13.0]):
        signal = algo.on_bar(bar)
        if signal == "buy":
            specs.append((float(bar["close"]), algo.order_spec()))
    assert specs, "expected a crossover buy"
    close, spec = specs[0]
    assert spec is not None
    assert spec.order_type == "limit"
    assert spec.post_only is True
    assert spec.limit_price == pytest.approx(close * (1 - 0.0002))
    # A hold bar clears the spec so a stale limit is never re-sent.
    algo.on_bar(_bars([13.0])[0])
    assert algo.order_spec() is None


def test_market_entry_is_the_default_and_needs_no_order_engine():
    algo = SmaCrossAlgorithm(fast=2, slow=4)
    assert algo.uses_order_engine is False
    assert algo.order_spec() is None


def test_maker_entry_fills_at_the_maker_fee_in_a_backtest():
    """The entry leg drops from 0.045% + 0.05% slippage to 0.015% with no slippage."""
    # A crossover on a flat base, then one bar that gaps up but dips through the resting limit.
    rows = [
        (10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0),
        (10.4, 10.0, 10.4),
        (10.45, 10.2, 10.55),
        (11.0, 10.5, 11.0),
        (11.6, 11.0, 11.6),
        (12.0, 11.5, 12.0),
    ]
    bars = [
        {
            "symbol": "X",
            "resolution": "1",
            "timestamp": index,
            "datetime_utc": "",
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
        }
        for index, (open_price, low, close) in enumerate(rows)
        for high in (max(open_price, close) * 1.001,)
    ]
    market = run_backtest(
        SmaCrossAlgorithm(fast=2, slow=4),
        bars,
        initial_cash=1_000.0,
        fee_rate=0.00045,
        slippage_rate=0.0005,
    )
    maker = run_backtest(
        SmaCrossAlgorithm(fast=2, slow=4, entry_order_mode="maker", entry_ttl_bars=3),
        bars,
        initial_cash=1_000.0,
        fee_rate=0.00045,
        slippage_rate=0.0005,
    )
    market_buys = [trade for trade in market.trades if trade.action == "buy"]
    maker_buys = [trade for trade in maker.trades if trade.action == "buy"]
    assert market_buys and maker_buys
    assert market_buys[0].liquidity == "taker"
    assert maker_buys[0].liquidity == "maker"
    # Maker fills at the limit price with no slippage, and pays 0.015% instead of 0.045%.
    assert maker_buys[0].price < market_buys[0].price
    assert maker_buys[0].fee < market_buys[0].fee


def test_backtest_namespace_turns_the_gate_on_for_one_minute_bars_only(tmp_path):
    from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest

    one_minute = namespace_for_strategy_backtest(
        "macd_cross", None, csv_path=tmp_path / "ARBUSDT_1.csv"
    )
    hourly = namespace_for_strategy_backtest(
        "macd_cross", None, csv_path=tmp_path / "ARBUSDT_60.csv"
    )
    assert one_minute.min_edge_over_cost == 1.0
    assert hourly.min_edge_over_cost == 0.0
    # An explicit value always wins, including "off".
    explicit = namespace_for_strategy_backtest(
        "macd_cross",
        default_strategy_namespace(min_edge_over_cost=0.0),
        csv_path=tmp_path / "ARBUSDT_1.csv",
    )
    assert explicit.min_edge_over_cost == 0.0


def test_backtest_namespace_resolves_the_roundtrip_cost_from_the_venue(tmp_path):
    from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest

    nobitex = namespace_for_strategy_backtest(
        "bollinger_mean_reversion", None, csv_path=tmp_path / "ARBIRT_1.csv"
    )
    hyperliquid = namespace_for_strategy_backtest(
        "bollinger_mean_reversion", None, csv_path=tmp_path / "ARBUSDT_1.csv"
    )
    assert nobitex.roundtrip_cost_pct == pytest.approx(0.009)
    assert hyperliquid.roundtrip_cost_pct == pytest.approx(0.0019)


def test_trend_strategies_default_to_momentum_confirmation_bounds():
    """The shared -3%/+3% bounds are mean-reversion semantics; trend needs the opposite sign."""
    from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest

    trend = namespace_for_strategy_backtest("sma_cross", None)
    mean_reversion = namespace_for_strategy_backtest("rsi_threshold", None)
    assert trend.buy_min_recent_return == 0.0
    assert trend.sell_max_recent_return == 0.0
    assert mean_reversion.buy_min_recent_return == -0.03
    assert mean_reversion.sell_max_recent_return == 0.03


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
    assert len(rules) == len(implemented_strategy_ids())
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
    assert len(manifest["strategies"]) == len(implemented_strategy_ids())
    assert manifest["best_strategy_id"] in {s["strategy_id"] for s in manifest["strategies"]}
    assert "buy_and_hold_return_pct" in manifest
    assert all("excess_vs_buy_hold_pct" in row for row in manifest["strategies"])
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
