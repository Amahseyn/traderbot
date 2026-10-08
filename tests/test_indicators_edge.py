from traderbot.utils.indicators import macd, rsi


def test_rsi_flat_market_reads_neutral():
    closes = [100.0] * 30
    values = rsi(closes, period=14)
    assert values[-1] == 50.0


def test_macd_signal_ignores_pre_line_zeros():
    closes = [100.0 + index * 0.1 for index in range(40)]
    line, signal, _hist = macd(closes, fast=12, slow=26, signal=9)
    first_line_index = 25
    assert signal[first_line_index] is not None
    assert signal[first_line_index - 1] is None
