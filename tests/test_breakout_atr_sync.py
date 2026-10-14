from traderbot.algorithms.strategies.breakout_atr import BreakoutAtrAlgorithm


def test_sync_open_position_clears_internal_long_state():
    algo = BreakoutAtrAlgorithm(lookback_bars=3, atr_period=2)
    algo._in_long = True
    algo._stop_price = 90.0
    algo.sync_open_position(False)
    assert not algo._in_long
    assert algo._stop_price is None
