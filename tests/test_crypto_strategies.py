import math

import pytest

from traderbot.algorithms.base import OrderSize
from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.strategies.dca import DcaAlgorithm
from traderbot.algorithms.strategies.grid import GridAlgorithm
from traderbot.algorithms.strategies.ma_trend import MaTrendAlgorithm
from traderbot.algorithms.strategies.momentum_shock import MomentumShockAlgorithm
from traderbot.algorithms.strategies.range_breakout import RangeBreakoutAlgorithm
from traderbot.algorithms.strategies.rsi_divergence import RsiDivergenceAlgorithm
from traderbot.algorithms.strategies.rsi_trend import RsiTrendAlgorithm
from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm
from traderbot.backtesting.benchmarks import build_dca_lump_sum_comparison
from traderbot.backtesting.engine import run_backtest
from traderbot.backtesting.rotation import build_cross_exchange_spreads, run_rotation_backtest

NEW_STRATEGY_IDS = (
    "ma_trend",
    "rsi_trend",
    "rsi_divergence",
    "range_breakout",
    "scalp_dip",
    "dca",
    "grid",
    "momentum_shock",
)
HOUR_SECONDS = 3600


def _bars(closes, volumes=None, spread=0.002, opens=None):
    rows = []
    for bar_index, close in enumerate(closes):
        open_price = opens[bar_index] if opens else (closes[bar_index - 1] if bar_index else close)
        rows.append(
            {
                "timestamp": bar_index * HOUR_SECONDS,
                "open": open_price,
                "high": max(open_price, close) * (1 + spread),
                "low": min(open_price, close) * (1 - spread),
                "close": close,
                "volume": volumes[bar_index] if volumes else 1.0,
            }
        )
    return rows


def _wavy_closes(count=400):
    return [100 + 10 * math.sin(index / 9) + 6 * math.sin(index / 31) + index * 0.03 for index in range(count)]


def _signals(algorithm, bars):
    algorithm.reset()
    return [algorithm.on_bar(bar) for bar in bars]


def _small_kwargs(strategy_id):
    namespace = default_strategy_namespace(
        trend_fast_period=10, trend_slow_period=30, trend_filter_period=20, dca_interval_bars=10
    )
    return strategy_kwargs_from_namespace(strategy_id, namespace)


@pytest.mark.parametrize("strategy_id", NEW_STRATEGY_IDS)
def test_new_strategy_has_no_lookahead(strategy_id):
    """Signals up to bar k must not change when later bars change."""
    bars = _bars(_wavy_closes(), volumes=[1.0 + (index % 7) for index in range(400)])
    algorithm = algorithm_for_id(strategy_id, **_small_kwargs(strategy_id))
    full = _signals(algorithm, bars)
    cut = 250
    altered = bars[:cut] + [dict(bar, close=bar["close"] * 1.5, high=bar["high"] * 1.5) for bar in bars[cut:]]
    assert _signals(algorithm, altered)[:cut] == full[:cut]
    assert _signals(algorithm, bars[:cut]) == full[:cut]


@pytest.mark.parametrize("strategy_id", NEW_STRATEGY_IDS)
def test_new_strategy_runs_in_backtest_engine(strategy_id):
    bars = _bars(_wavy_closes(), volumes=[1.0 + (index % 7) for index in range(400)])
    algorithm = algorithm_for_id(strategy_id, **_small_kwargs(strategy_id))
    for execution in ("close", "next_open"):
        result = run_backtest(algorithm, bars, fee_rate=0.001, execution=execution)
        assert result.final_equity > 0
        for trade in result.trades:
            assert trade.position_after >= 0 and trade.cash_after >= -1e-6


def test_ma_trend_golden_cross_exit_below_slow_and_adds():
    closes = [100.0] * 40 + [100 + index for index in range(1, 30)] + [125, 127, 129] + [90.0] * 5
    algorithm = MaTrendAlgorithm(trend_fast_period=5, trend_slow_period=20, trend_max_adds=2)
    signals = _signals(algorithm, _bars(closes))
    assert "buy" in signals
    first_buy = signals.index("buy")
    assert "sell" in signals[first_buy:]
    sell_index = signals.index("sell", first_buy)
    assert closes[sell_index] < sum(closes[sell_index - 19 : sell_index + 1]) / 20


def test_ma_trend_trailing_stop_and_size():
    closes = [100.0] * 30 + [100 + 2 * index for index in range(1, 25)] + [140.0, 128.0]
    algorithm = MaTrendAlgorithm(trend_fast_period=5, trend_slow_period=20, trailing_stop_pct=0.05)
    signals = _signals(algorithm, _bars(closes, spread=0.0))
    assert signals[-2] == "sell"  # 140 is more than 5% under the 148 peak
    assert signals[-1] == "hold"


def test_rsi_trend_enters_on_strength_and_exits_on_weakness():
    closes = [100.0 - 0.2 * index for index in range(60)] + [88 + 0.8 * index for index in range(30)]
    closes += [closes[-1] - 1.5 * index for index in range(1, 15)]
    signals = _signals(RsiTrendAlgorithm(period=14, trend_filter_period=20), _bars(closes))
    first_buy = signals.index("buy")
    assert first_buy >= 60
    assert "sell" in signals[first_buy:]


def test_rsi_divergence_buys_after_confirmation_and_sets_stop():
    closes = [100 - index for index in range(15)] + [86, 88, 90, 89, 87]
    closes += [85.5 + 0.1 * index for index in range(1)] + [85.8, 86.5, 88, 90, 92, 94]
    lows_override = {14: 84.0, 20: 83.0}
    bars = _bars(closes, spread=0.001)
    for bar_index, low in lows_override.items():
        bars[bar_index]["low"] = low
    algorithm = RsiDivergenceAlgorithm(period=5, swing_window_bars=2, divergence_rsi_level=50)
    signals = _signals(algorithm, bars)
    assert "buy" in signals
    assert signals.index("buy") > 20 + 2
    assert algorithm._stop_price < 83.0


def test_range_breakout_needs_volume_and_hits_target():
    closes = [100 + (index % 2) * 0.5 for index in range(20)] + [102.0, 101.5]
    quiet = _bars(closes, volumes=[1.0] * 22, spread=0.001)
    assert "buy" not in _signals(RangeBreakoutAlgorithm(lookback_bars=10, breakout_volume_multiplier=2.0), quiet)
    loud = _bars(closes + [104.0], volumes=[1.0] * 20 + [5.0, 1.0, 1.0], spread=0.001)
    signals = _signals(RangeBreakoutAlgorithm(lookback_bars=10, breakout_volume_multiplier=2.0), loud)
    assert signals[20] == "buy"
    assert signals[21] == "sell"  # measured-move target (range high + height) reached


def test_scalp_dip_take_profit_stop_and_session_flat():
    closes = [100.0] * 10 + [99.4]
    opens = [100.0] * 10 + [99.2]
    algorithm = ScalpDipAlgorithm(dip_lookback_bars=5, dip_pct=0.005, take_profit_pct=0.0075, stop_loss_pct=0.005)
    bars = _bars(closes + [100.3], opens=opens + [99.4], spread=0.0)
    signals = _signals(algorithm, bars)
    assert signals[10] == "buy" and signals[11] == "sell"
    stop_bars = _bars(closes + [98.8], opens=opens + [99.4], spread=0.0)
    signals = _signals(algorithm, stop_bars)
    assert signals[11] == "sell" and algorithm._cooldown_bars == 3
    session = ScalpDipAlgorithm(dip_lookback_bars=5, dip_pct=0.005, session_end_hour_utc=11)
    signals = _signals(session, _bars(closes + [99.5], opens=opens + [99.4], spread=0.0))
    assert signals[11] == "sell"


def test_scalp_dip_size_never_increases_after_loss():
    algorithm = ScalpDipAlgorithm(scalp_position_fraction=0.5)
    sizes = set()
    for bar in _bars(_wavy_closes(300), spread=0.004):
        if algorithm.on_bar(bar) == "buy":
            sizes.add(algorithm.order_size().target_exposure)
    assert sizes <= {0.5}


def test_dca_buys_fixed_amounts_and_compares_lump_sum():
    bars = _bars([100.0 + index for index in range(50)])
    algorithm = DcaAlgorithm(dca_interval_bars=10, dca_order_count=4)
    result = run_backtest(algorithm, bars, initial_cash=1000.0)
    spends = [trade.cash_before - trade.cash_after for trade in result.trades]
    assert [round(spend, 6) for spend in spends] == [250.0] * 4
    comparison = build_dca_lump_sum_comparison(algorithm, bars, initial_cash=1000.0, fee_rate=0.0)
    assert comparison["dca_orders"] == 4
    assert comparison["lump_sum_return_pct"] > comparison["dca_return_pct"]


def test_grid_rebalances_by_band_and_shuts_down_on_breakout():
    closes = [100.0] * 5 + [97.0, 95.5, 99.0, 103.0, 120.0, 100.0]
    algorithm = GridAlgorithm(lookback_bars=5, grid_range_pct=0.05, grid_levels=5, grid_breakout_pct=0.01)
    signals = _signals(algorithm, _bars(closes))
    assert signals[5] == "buy" and signals[6] == "buy"
    assert signals[8] == "sell"
    assert signals[9] == "sell" and algorithm.is_shut_down
    assert signals[10] == "hold"


def test_grid_partial_fills_in_engine():
    closes = [100.0] * 5 + [97.0, 95.5, 99.0, 103.0]
    result = run_backtest(GridAlgorithm(lookback_bars=5, grid_levels=5), _bars(closes), initial_cash=1000.0)
    assert len(result.trades) >= 3
    assert 0 < result.trades[0].position_after < result.trades[1].position_after


def test_momentum_shock_proxy_needs_return_and_volume():
    closes = [100 + 0.1 * (index % 3) for index in range(30)] + [106.0] + [106.0] * 5
    volumes = [1.0] * 30 + [5.0] + [1.0] * 5
    signals = _signals(MomentumShockAlgorithm(lookback_bars=20, shock_hold_bars=3), _bars(closes, volumes=volumes))
    assert signals[30] == "buy" and signals[33] == "sell"
    no_volume = _signals(MomentumShockAlgorithm(lookback_bars=20), _bars(closes))
    assert "buy" not in no_volume


def test_rotation_holds_strongest_symbol_and_spreads_scanner():
    up = _bars([100 + index for index in range(60)])
    down = _bars([100 - 0.5 * index for index in range(60)])
    result = run_rotation_backtest({"UP": up, "DOWN": down}, momentum_bars=5, rebalance_bars=5)
    assert result.holdings_log[0]["holdings"] == ["UP"]
    assert result.return_pct > 0
    venue_b = [dict(bar, close=bar["close"] * 1.01) for bar in up]
    spreads = build_cross_exchange_spreads(up, venue_b, fee_rate_a=0.001, fee_rate_b=0.001, min_net_spread=0.005)
    assert spreads and spreads[0]["buy_venue"] == "a"


def test_online_logistic_learns_persistent_trend_without_lookahead():
    from traderbot.algorithms.strategies.online_logistic import OnlineLogisticAlgorithm

    closes = [100 * (1.002 ** index) * (1 + 0.003 * math.sin(index)) for index in range(400)]
    bars = _bars(closes, volumes=[1.0 + (index % 5) for index in range(400)])
    algorithm = OnlineLogisticAlgorithm(ml_warmup_samples=50, ml_horizon_bars=3)
    full = _signals(algorithm, bars)
    assert "buy" in full
    assert algorithm.last_probability is not None and algorithm.last_probability > 0.5
    cut = 200
    altered = bars[:cut] + [dict(bar, close=bar["close"] * 0.5) for bar in bars[cut:]]
    assert _signals(algorithm, altered)[:cut] == full[:cut]


def test_pairs_backtest_switches_to_cheap_leg_and_zscores_are_causal():
    from traderbot.backtesting.pairs import build_pair_zscores, run_pairs_backtest

    base = [100 * (1 + 0.01 * math.sin(index / 5)) for index in range(300)]
    closes_b = [value * (1 + 0.001 * index) for index, value in enumerate(base)]
    closes_a = [b * (1 + 0.03 * math.sin(index / 7)) for index, b in enumerate(closes_b)]
    zscores = build_pair_zscores(closes_a, closes_b, pair_lookback_bars=40)
    altered = build_pair_zscores(closes_a[:150] + [value * 2 for value in closes_a[150:]], closes_b, pair_lookback_bars=40)
    assert zscores[:150] == altered[:150]
    result = run_pairs_backtest(_bars(closes_a), _bars(closes_b), pair_lookback_bars=40, pair_entry_z=1.5)
    positions = {trade["position"] for trade in result.trades}
    assert 1 in positions and -1 in positions and 0 in positions
    neutral = run_pairs_backtest(_bars(closes_a), _bars(closes_b), pair_lookback_bars=40, pair_entry_z=1.5, mode="market_neutral")
    assert neutral.final_equity > 0
