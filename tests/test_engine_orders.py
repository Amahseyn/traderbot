"""Limit / bracket / short execution in the backtest engine (SimBroker)."""

import pytest

from traderbot.algorithms.base import Algorithm, OrderSize, OrderSpec
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm
from traderbot.backtesting.engine import run_backtest
from traderbot.backtesting.fills import Bracket, limit_fill_price, post_only_accepts


def _bar(ts, o, h, l, c, **extra):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0, **extra}


class Scripted(Algorithm):
    """Emits a fixed (signal, size, spec) per bar index."""

    name = "scripted"
    uses_position_sizing = True

    def __init__(self, script, allow_short=False):
        self.script = script
        self.allow_short = allow_short
        self.reset()

    def reset(self):
        self.i = -1
        self.fills = []
        self.expired = []

    def on_bar(self, bar):
        self.i += 1
        self._cur = self.script.get(self.i, ("hold", None, None))
        return self._cur[0]

    def order_size(self):
        return self._cur[1]

    def order_spec(self):
        return self._cur[2]

    def on_fill(self, side, price, size, reason, position):
        self.fills.append((side, price, reason, position))

    def on_order_expired(self, side):
        self.expired.append(side)


def test_limit_fill_requires_trade_through():
    assert limit_fill_price("buy", 99.0, _bar(0, 100, 100, 99.0, 99.5)) is None
    assert limit_fill_price("buy", 99.0, _bar(0, 100, 100, 98.9, 99.5)) == 99.0
    assert limit_fill_price("sell", 101.0, _bar(0, 100, 101.1, 100, 100)) == 101.0
    assert post_only_accepts("buy", 99.0, 100.0) and not post_only_accepts("buy", 100.0, 100.0)


def test_bracket_stop_gaps_fill_at_open():
    bracket = Bracket.from_fill(1, 100.0, take_profit_pct=0.01, stop_loss_pct=0.01)
    assert bracket.exit_for_bar(_bar(0, 98.0, 98.5, 97.0, 98.0)) == (98.0, "stop_loss")
    assert bracket.exit_for_bar(_bar(0, 100.0, 101.5, 98.5, 100.0)) == (99.0, "stop_loss")  # stop first
    assert bracket.exit_for_bar(_bar(0, 100.0, 101.5, 99.5, 100.0)) == (101.0, "take_profit")


def test_limit_entry_maker_fee_and_take_profit_at_limit():
    spec = OrderSpec(order_type="limit", limit_price=99.0, ttl_bars=3, take_profit_pct=0.02, stop_loss_pct=0.02)
    algo = Scripted({0: ("buy", OrderSize(target_exposure=1.0), spec)})
    bars = [
        _bar(0, 100, 100, 99.5, 100),
        _bar(1, 100, 100, 99.2, 99.5),  # not reached
        _bar(2, 99.5, 99.6, 98.5, 99.0),  # filled at 99.0
        _bar(3, 99.0, 101.5, 99.0, 101.0),  # TP 100.98 maker
    ]
    result = run_backtest(algo, bars, fee_rate=0.00045, slippage_rate=0.0005, initial_cash=1000.0)
    buy, sell = result.trades
    assert (buy.price, buy.liquidity, buy.reason) == (99.0, "maker", "limit")
    assert sell.reason == "take_profit" and sell.price == pytest.approx(99.0 * 1.02)
    assert sell.fee == pytest.approx(sell.size * sell.price * 0.00015)
    assert result.trades[-1].position_after == 0.0
    assert algo.fills[0][1] == 99.0


def test_limit_entry_expires_after_ttl():
    spec = OrderSpec(order_type="limit", limit_price=95.0, ttl_bars=2)
    algo = Scripted({0: ("buy", OrderSize(target_exposure=1.0), spec)})
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(5)]
    result = run_backtest(algo, bars, fee_rate=0.00045)
    assert result.trades == [] and algo.expired == ["buy"]


def test_post_only_limit_that_would_cross_is_rejected():
    spec = OrderSpec(order_type="limit", limit_price=101.0, ttl_bars=2)
    algo = Scripted({0: ("buy", OrderSize(target_exposure=1.0), spec)})
    result = run_backtest(algo, [_bar(i, 100, 102, 98, 100) for i in range(3)], fee_rate=0.00045)
    assert result.trades == [] and algo.expired == ["buy"]


def test_market_entry_bracket_stop_pays_taker_and_slippage():
    spec = OrderSpec(order_type="market", take_profit_pct=0.02, stop_loss_pct=0.01)
    algo = Scripted({0: ("buy", OrderSize(target_exposure=1.0), spec)})
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 100), _bar(2, 100, 100, 98, 98.5)]
    result = run_backtest(algo, bars, fee_rate=0.00045, slippage_rate=0.0005, execution="next_open")
    buy, stop = result.trades
    assert buy.price == pytest.approx(100 * 1.0005)
    assert stop.reason == "stop_loss" and stop.liquidity == "taker"
    # Stop measured from the actual (slipped) fill price, then slipped again.
    assert stop.price == pytest.approx(100 * 1.0005 * 0.99 * 0.9995)


def test_short_round_trip_profits_on_drop_and_nobitex_stays_long_only():
    script = {0: ("sell", OrderSize(target_exposure=-1.0), None), 2: ("buy", OrderSize(target_exposure=0.0), None)}
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 90, 90), _bar(2, 90, 90, 90, 90), _bar(3, 90, 90, 90, 90)]
    algo = Scripted(script, allow_short=True)
    result = run_backtest(algo, bars, fee_rate=0.0, execution="close", initial_cash=1000.0)
    assert [t.action for t in result.trades] == ["sell", "buy"]
    assert result.trades[0].position_after == pytest.approx(-10.0)
    assert result.final_equity == pytest.approx(1100.0)
    irt = [dict(b, symbol="BTCIRT") for b in bars]
    algo = Scripted(script, allow_short=True)
    assert run_backtest(algo, irt, fee_rate=0.0, execution="close").trades == []


def _dip_bars():
    bars = [_bar(i, 100, 100.1, 99.9, 100) for i in range(12)]
    bars.append(_bar(12, 99.2, 99.6, 99.1, 99.5))  # 0.5% dip that closes green -> signal
    bars.append(_bar(13, 99.5, 99.6, 99.3, 99.5))
    bars.append(_bar(14, 99.5, 101.0, 99.4, 100.8))
    return bars


def test_scalp_dip_bracket_mode_exits_at_take_profit_price():
    algo = ScalpDipAlgorithm(scalp_order_mode="bracket", take_profit_pct=0.01, stop_loss_pct=0.01)
    result = run_backtest(algo, _dip_bars(), fee_rate=0.00045, slippage_rate=0.0005)
    buy, tp = result.trades
    assert buy.reason == "market" and tp.reason == "take_profit"
    assert tp.price == pytest.approx(buy.price * 1.01) and tp.liquidity == "maker"


def test_scalp_dip_maker_mode_posts_below_close():
    algo = ScalpDipAlgorithm(scalp_order_mode="maker", entry_offset_pct=0.001, take_profit_pct=0.01)
    result = run_backtest(algo, _dip_bars(), fee_rate=0.00045)
    buy = result.trades[0]
    assert buy.liquidity == "maker" and buy.price == pytest.approx(99.5 * 0.999)


def test_scalp_dip_atr_mode_and_volume_filter():
    algo = ScalpDipAlgorithm(scalp_threshold_mode="atr", dip_atr_mult=1.0, atr_period=5)
    assert run_backtest(algo, _dip_bars(), fee_rate=0.0).trades
    bars = _dip_bars()
    bars[12]["volume"] = 0.1
    algo = ScalpDipAlgorithm(min_volume_ratio=1.5)
    assert run_backtest(algo, bars, fee_rate=0.0).trades == []
    bars = _dip_bars()
    bars[12]["spread_pct"] = 0.01
    algo = ScalpDipAlgorithm(max_spread_pct=0.001)
    assert run_backtest(algo, bars, fee_rate=0.0).trades == []


def test_scalp_preset_fills_defaults_but_explicit_flags_win():
    algo = algorithm_for_id("scalp_dip", **strategy_kwargs_from_namespace("scalp_dip", default_strategy_namespace(scalp_preset="5m")))
    assert algo.scalp_order_mode == "maker" and algo.take_profit_pct == 0.006
    algo = algorithm_for_id("scalp_dip", **strategy_kwargs_from_namespace("scalp_dip", default_strategy_namespace(scalp_preset="5m", scalp_order_mode="bracket")))
    assert algo.scalp_order_mode == "bracket"


def test_legacy_market_strategy_untouched_by_on_fill():
    algo = ScalpDipAlgorithm()
    result = run_backtest(algo, _dip_bars(), fee_rate=0.001, execution="next_open")
    assert result.trades[0].liquidity == "taker"
