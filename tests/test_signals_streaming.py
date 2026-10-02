from traderbot.algorithms.signals import signal_from_cross, signal_from_levels, signal_from_thresholds
from traderbot.algorithms.streaming import ema_init, ema_update, rolling_mean_init, rolling_mean_update


def test_signal_from_levels():
    assert signal_from_levels(None, 1.0) == "hold"
    assert signal_from_levels(2.0, 1.0) == "buy"
    assert signal_from_levels(1.0, 2.0) == "sell"


def test_signal_from_cross():
    assert signal_from_cross(1.0, 2.0, 3.0, 2.0) == "buy"
    assert signal_from_cross(3.0, 2.0, 1.0, 2.0) == "sell"


def test_signal_from_thresholds():
    assert signal_from_thresholds(25.0, buy_at_or_below=30.0, sell_at_or_above=70.0) == "buy"
    assert signal_from_thresholds(75.0, buy_at_or_below=30.0, sell_at_or_above=70.0) == "sell"


def test_rolling_mean_and_ema():
    rm = rolling_mean_init(3)
    assert rolling_mean_update(rm, 1.0) is None
    assert rolling_mean_update(rm, 2.0) is None
    assert rolling_mean_update(rm, 3.0) == 2.0

    em = ema_init(3)
    assert ema_update(em, 10.0) == 10.0
    assert ema_update(em, 20.0) > 10.0
