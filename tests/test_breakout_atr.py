from traderbot.algorithms.strategies.breakout_atr import BreakoutAtrAlgorithm


def _bar(index: int, close: float, *, high: float | None = None, low: float | None = None) -> dict:
    return {
        "timestamp": index,
        "open": close,
        "high": high if high is not None else close + 0.5,
        "low": low if low is not None else close - 0.5,
        "close": close,
        "volume": 1.0,
    }


def test_breakout_atr_stop_triggers_sell():
    algo = BreakoutAtrAlgorithm(lookback_bars=2, atr_period=2, atr_multiplier=0.1, stop_atr_multiplier=1.0)
    bars = [
        _bar(0, 100.0),
        _bar(1, 100.0),
        _bar(2, 100.0),
        _bar(3, 120.0, high=125.0, low=119.0),
        _bar(4, 90.0, high=91.0, low=89.0),
    ]
    signals = [algo.on_bar(bar) for bar in bars]
    assert signals[3] == "buy"
    assert signals[4] == "sell"
