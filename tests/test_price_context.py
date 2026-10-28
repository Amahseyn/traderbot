import pytest

from traderbot.algorithms.price_context import (
    apply_mean_reversion_context,
    recent_cumulative_return,
    recent_return_gate,
    required_signal_edge_pct,
    resolve_roundtrip_cost_pct,
    signal_clears_cost,
    trend_edge_window_bars,
    trend_signal_clears_cost,
)
from traderbot.algorithms.validators import validate_cost_edge, validate_price_context


def test_recent_cumulative_return():
    assert recent_cumulative_return([100.0, 110.0], 1) == pytest.approx(0.1)
    assert recent_cumulative_return([100.0], 1) is None


def test_apply_mean_reversion_context_blocks_falling_knife_buy():
    closes = [100.0, 99.0, 98.0, 97.0]
    assert (
        apply_mean_reversion_context(
            "buy",
            closes,
            context_bars=3,
            buy_min_recent_return=-0.01,
            sell_max_recent_return=0.03,
        )
        == "hold"
    )


def test_apply_intrahour_context_skips_filter_when_fine_return_missing():
    from traderbot.algorithms.price_context import apply_intrahour_context

    bar = {"close": 1.0}
    assert apply_intrahour_context("buy", bar, buy_min_fine_last_5m=-0.01) == "buy"
    assert apply_intrahour_context("sell", bar, sell_max_fine_last_5m=0.01) == "sell"


def test_apply_intrahour_context_blocks_buy_on_weak_fine_tail():
    from traderbot.algorithms.price_context import apply_intrahour_context

    bar = {"fine_return_last_5m": -0.02}
    assert apply_intrahour_context("buy", bar, buy_min_fine_last_5m=-0.01) == "hold"
    assert apply_intrahour_context("buy", bar, buy_min_fine_last_5m=-0.03) == "buy"


def test_validate_price_context_ordering():
    validate_price_context(0, -0.05, 0.05)
    with pytest.raises(ValueError):
        validate_price_context(3, 0.05, -0.05)


def test_resolve_roundtrip_cost_pct_defaults_to_hyperliquid_taker():
    assert resolve_roundtrip_cost_pct(None) == pytest.approx(0.0019)
    assert resolve_roundtrip_cost_pct(0.0) == 0.0
    assert resolve_roundtrip_cost_pct(0.009) == pytest.approx(0.009)


def test_required_signal_edge_pct_scales_with_the_venue():
    # Break-even (1x) on Hyperliquid taker and on Nobitex retail spot.
    assert required_signal_edge_pct(0.0019, 1.0) == pytest.approx(0.0019)
    assert required_signal_edge_pct(0.009, 1.0) == pytest.approx(0.009)
    assert required_signal_edge_pct(0.0019, 2.0) == pytest.approx(0.0038)
    # 0 disables the gate; a negative multiple is a caller bug but must not tighten it.
    assert required_signal_edge_pct(0.0019, 0.0) == 0.0
    assert required_signal_edge_pct(0.0019, -1.0) == 0.0


def test_signal_clears_cost_is_a_magnitude_gate_for_mean_reversion():
    # A 0.04% band-to-mean distance cannot pay a 0.19% roundtrip.
    assert not signal_clears_cost(0.0004, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    assert signal_clears_cost(0.0025, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    # Direction is irrelevant: fading a pop and fading a dip both use the magnitude.
    assert signal_clears_cost(-0.0025, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    # Gate off, and "no computable edge" rejected once it is on.
    assert signal_clears_cost(None, roundtrip_cost_pct=0.0019, min_edge_over_cost=0.0)
    assert not signal_clears_cost(None, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)


def test_trend_signal_clears_cost_requires_momentum_in_the_trade_direction():
    # A cross that fires after a 0.02% drift cannot pay 0.19%, even if it is right.
    assert not trend_signal_clears_cost("buy", 0.0002, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    assert trend_signal_clears_cost("buy", 0.0030, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    # The sell needs a decline, not a rally of the same size.
    assert trend_signal_clears_cost("sell", -0.0030, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    assert not trend_signal_clears_cost("sell", 0.0030, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)
    assert trend_signal_clears_cost("buy", None, roundtrip_cost_pct=0.0019, min_edge_over_cost=0.0)
    assert not trend_signal_clears_cost("buy", None, roundtrip_cost_pct=0.0019, min_edge_over_cost=1.0)


def test_trend_edge_window_bars_follows_context_then_slow_period():
    assert trend_edge_window_bars(20, 26) == 20
    assert trend_edge_window_bars(0, 26) == 26
    assert trend_edge_window_bars(0, 0) == 1


def test_recent_return_gate_trend_defaults_need_momentum_confirmation():
    falling = [100.0, 99.0, 98.0]
    assert recent_return_gate(
        "buy",
        falling,
        context_bars=2,
        buy_min_recent_return=0.0,
        sell_max_recent_return=0.0,
    ) == "hold"
    assert recent_return_gate(
        "sell",
        falling,
        context_bars=2,
        buy_min_recent_return=0.0,
        sell_max_recent_return=0.0,
    ) == "sell"
    # context_bars=0 keeps the legacy blind-threshold behavior.
    assert recent_return_gate(
        "buy",
        falling,
        context_bars=0,
        buy_min_recent_return=0.0,
        sell_max_recent_return=0.0,
    ) == "buy"


def test_validate_cost_edge_rejects_negative_multiple_and_bad_cost():
    validate_cost_edge(None, None)
    validate_cost_edge(0.0, 0.0)
    validate_cost_edge(2.0, 0.0019)
    with pytest.raises(ValueError):
        validate_cost_edge(-1.0, 0.0019)
    with pytest.raises(ValueError):
        validate_cost_edge(1.0, 1.5)
