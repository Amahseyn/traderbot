import pytest

from traderbot.algorithms.base import Algorithm, OrderSize
from traderbot.backtesting.engine import run_backtest
from traderbot.backtesting.param_bounds import float_bounds, param_value_error
from traderbot.backtesting.sweep import parse_sweep_param, sweep_rank_key
from traderbot.backtesting.trade_stats import DEFAULT_MIN_TRADES, round_trip_returns, trade_stats


class Alternate(Algorithm):
    name = "alternate"

    def reset(self):
        self.i = -1

    def on_bar(self, bar):
        self.i += 1
        return "buy" if self.i % 2 == 0 else "sell"


def _bars(closes):
    return [{"timestamp": i, "open": c, "high": c, "low": c, "close": c, "volume": 1.0} for i, c in enumerate(closes)]


def test_round_trip_returns_are_net_of_fees():
    algo = Alternate()
    algo.reset()
    result = run_backtest(algo, _bars([100, 110, 100, 90, 100]), fee_rate=0.001, execution="close")
    returns = round_trip_returns(result)
    assert len(returns) == 2
    assert returns[0] == pytest.approx(110 / 100 * (1 - 0.001) ** 2 - 1, rel=1e-9)
    stats = trade_stats(result)
    assert stats["round_trips"] == 2 and stats["trade_win_rate"] == 0.5


def test_edge_rank_prefers_significant_per_trade_edge_over_raw_return():
    lucky = {"eligible": True, "return_pct": 9.0, "avg_trade_net_pct": 0.5, "trade_t_stat": 0.8}
    steady = {"eligible": True, "return_pct": 4.0, "avg_trade_net_pct": 0.05, "trade_t_stat": 3.1}
    ranked = sorted([lucky, steady], key=lambda r: sweep_rank_key(r, rank_by="edge"), reverse=True)
    assert ranked[0] is steady
    assert sorted([lucky, steady], key=lambda r: sweep_rank_key(r, rank_by="return_pct"), reverse=True)[0] is lucky


def test_min_trades_default_is_30():
    from traderbot.backtesting.sweep import SweepOptions
    from traderbot.backtesting.validation import ValidationOptions

    assert DEFAULT_MIN_TRADES == 30
    assert SweepOptions(strategy_id="sma_cross", param_grid={"fast": [5]}).min_trades == 30
    assert ValidationOptions(strategy_id="sma_cross", param_grid={"fast": [5]}).min_trades == 30


@pytest.mark.parametrize(
    "name,default",
    [("stop_loss_pct", 0.005), ("take_profit_pct", 0.0075), ("scalp_position_fraction", 1.0),
     ("mm_inventory_skew", 0.0), ("trailing_stop_pct", 0.0), ("oversold", 30.0), ("mm_half_spread_pct", 0.0005)],
)
def test_float_bounds_stay_valid(name, default):
    low, high = float_bounds(name, default)
    assert low >= 0 and low <= default <= high
    if "fraction" in name or "skew" in name:
        assert high <= 1.0


def test_sweep_rejects_negative_stop_and_fraction_above_one():
    assert param_value_error("stop_loss_pct", -0.01)
    assert param_value_error("scalp_position_fraction", 1.5)
    assert param_value_error("buy_min_recent_return", -0.05) is None
    with pytest.raises(ValueError):
        parse_sweep_param("stop_loss_pct=0.004,-0.002")
    assert parse_sweep_param("stop_loss_pct=0.004,0.006")[1] == [0.004, 0.006]


def test_bar_cache_merges_and_reports_gaps(tmp_path):
    from traderbot.data.bar_cache import find_gaps, read_cached_bars, update_hyperliquid_cache

    def bar(ts):
        return {"timestamp": ts, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1, "symbol": "BTCUSDT",
                "resolution": "1"}

    calls = []

    def fake_fetch(*, src, resolution, history_from_unix_seconds, history_to_unix_seconds):
        calls.append(history_from_unix_seconds)
        return [bar(t) for t in range(history_from_unix_seconds - history_from_unix_seconds % 60,
                                      history_to_unix_seconds - 60, 60) if t >= history_from_unix_seconds]

    path, bars = update_hyperliquid_cache("BTC", "1", cache_dir=tmp_path, lookback_days=0.01, fetch=fake_fetch,
                                          now=6000)
    first_len = len(bars)
    path, bars = update_hyperliquid_cache("BTC", "1", cache_dir=tmp_path, fetch=fake_fetch, now=9000)
    assert calls[1] == bars[first_len - 1]["timestamp"] + 60  # resumes after the cached tail
    assert len(bars) > first_len
    assert read_cached_bars(path)[-1]["timestamp"] == bars[-1]["timestamp"]
    assert find_gaps(bars, 60) == []


def test_walk_forward_reports_only_out_of_sample_segments():
    import math

    from traderbot.backtesting.walk_forward import WalkForwardOptions, run_walk_forward

    closes = [100 + 5 * math.sin(i / 7) for i in range(1200)]
    bars = [{"timestamp": i * 60, "open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1.0}
            for i, c in enumerate(closes)]
    payload = run_walk_forward(
        WalkForwardOptions(strategy_id="sma_cross", param_grid={"fast": [3, 5], "slow": [20]}, bars=bars,
                           train_bars=400, test_bars=200, warmup_bars=50, min_trades=2, fee=0.0005, slippage=0.0)
    )
    assert len(payload["folds"]) == 4
    assert all(fold["test_start"] > fold["train_start"] for fold in payload["folds"])
    assert payload["oos_round_trips"] >= 0 and "oos_t_stat" in payload
