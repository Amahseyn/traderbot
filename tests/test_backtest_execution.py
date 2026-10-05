import pytest

from traderbot.algorithms.base import Algorithm
from traderbot.backtesting.engine import run_backtest


class ScriptedAlgorithm(Algorithm):
    """Replays a fixed signal per bar and records every bar it sees."""

    name = "scripted"

    def __init__(self, signals):
        self._signals = list(signals)
        self.seen_timestamps: list[int] = []
        self.calls = 0

    def reset(self) -> None:
        self.seen_timestamps.clear()
        self.calls = 0

    def on_bar(self, bar):
        self.calls += 1
        self.seen_timestamps.append(int(bar["timestamp"]))
        if self.calls - 1 < len(self._signals):
            return self._signals[self.calls - 1]
        return "hold"


def _bars(opens, closes):
    return [
        {
            "timestamp": index * 60,
            "open": open_price,
            "high": max(open_price, close),
            "low": min(open_price, close),
            "close": close,
            "volume": 1.0,
        }
        for index, (open_price, close) in enumerate(zip(opens, closes))
    ]


def test_close_fill_applies_fee():
    bars = _bars([100.0, 110.0, 120.0], [100.0, 110.0, 120.0])
    result = run_backtest(
        ScriptedAlgorithm(["buy", "hold", "sell"]),
        bars,
        initial_cash=1000.0,
        fee_rate=0.01,
    )
    position = (1000.0 - 10.0) / 100.0
    proceeds = position * 120.0
    expected_fees = 10.0 + proceeds * 0.01
    assert result.final_equity == pytest.approx(proceeds - proceeds * 0.01)
    assert result.total_fees == pytest.approx(expected_fees)
    assert [trade.price for trade in result.trades] == [100.0, 120.0]


def test_close_fill_applies_slippage_against_trader():
    bars = _bars([100.0, 110.0], [100.0, 110.0])
    result = run_backtest(
        ScriptedAlgorithm(["buy", "sell"]),
        bars,
        initial_cash=1000.0,
        slippage_rate=0.01,
    )
    buy_price, sell_price = (trade.price for trade in result.trades)
    assert buy_price == pytest.approx(101.0)
    assert sell_price == pytest.approx(108.9)
    assert result.final_equity == pytest.approx((1000.0 / 101.0) * 108.9)


def test_next_open_fills_at_next_bar_open():
    bars = _bars([100.0, 102.0, 104.0], [100.0, 102.0, 104.0])
    result = run_backtest(
        ScriptedAlgorithm(["buy", "sell", "hold"]),
        bars,
        initial_cash=1000.0,
        execution="next_open",
    )
    assert [trade.price for trade in result.trades] == [102.0, 104.0]
    assert result.final_equity == pytest.approx((1000.0 / 102.0) * 104.0)


def test_next_open_last_bar_signal_expires_unfilled():
    bars = _bars([100.0, 110.0], [100.0, 110.0])
    result = run_backtest(
        ScriptedAlgorithm(["hold", "buy"]),
        bars,
        initial_cash=1000.0,
        execution="next_open",
    )
    assert result.trades == []
    assert result.final_equity == pytest.approx(1000.0)


def test_next_open_never_peeks_beyond_signal_bar():
    closes = [100.0, 101.0, 150.0, 151.0]
    bars = _bars(closes, closes)
    algo = ScriptedAlgorithm(["hold", "buy", "hold", "sell"])
    result = run_backtest(algo, bars, initial_cash=1000.0, execution="next_open")
    assert algo.seen_timestamps == [0, 60, 120, 180]
    assert algo.calls == 4
    # Buy signal on bar 1 fills at bar 2 open (150). The sell signal sits on the
    # last bar, so it expires and the position is marked at the last close.
    assert len(result.trades) == 1
    assert result.trades[0].price == pytest.approx(150.0)
    assert result.final_equity == pytest.approx((1000.0 / 150.0) * 151.0)


def test_close_execution_matches_next_open_on_flat_opens():
    prices = [100.0, 102.0, 101.0, 105.0]
    bars = _bars(prices, prices)
    close_result = run_backtest(
        ScriptedAlgorithm(["buy", "hold", "hold", "sell"]), bars, initial_cash=1000.0
    )
    assert close_result.final_equity == pytest.approx((1000.0 / 100.0) * 105.0)


def test_rejects_bad_inputs():
    bars = _bars([100.0], [100.0])
    with pytest.raises(ValueError):
        run_backtest(ScriptedAlgorithm(["hold"]), [], initial_cash=1000.0)
    with pytest.raises(ValueError):
        run_backtest(ScriptedAlgorithm(["hold"]), bars, initial_cash=1000.0, fee_rate=1.0)
    with pytest.raises(ValueError):
        run_backtest(ScriptedAlgorithm(["hold"]), bars, initial_cash=1000.0, slippage_rate=-0.1)
    with pytest.raises(ValueError):
        run_backtest(ScriptedAlgorithm(["hold"]), bars, initial_cash=1000.0, execution="market")
