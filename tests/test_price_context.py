import pytest

from traderbot.algorithms.price_context import (
    apply_mean_reversion_context,
    recent_cumulative_return,
)
from traderbot.algorithms.validators import validate_price_context


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
