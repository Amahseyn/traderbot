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


def test_validate_price_context_ordering():
    validate_price_context(0, -0.05, 0.05)
    with pytest.raises(ValueError):
        validate_price_context(3, 0.05, -0.05)
