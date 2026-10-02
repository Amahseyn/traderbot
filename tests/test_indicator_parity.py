"""Parity between batch ML indicators and incremental strategy usage."""

from __future__ import annotations

import math

import pytest

from traderbot.algorithms.bands import bollinger_init, bollinger_levels, bollinger_update
from traderbot.algorithms.streaming import ema_init, ema_update, rolling_mean_init, rolling_mean_update
from traderbot.ml.features import atr, build_feature_rows, macd, rsi


def _synthetic_bars(n: int = 80) -> list[dict]:
    bars = []
    price = 100.0
    for i in range(n):
        price *= 1.0 + 0.002 * math.sin(i / 5.0)
        bars.append(
            {
                "timestamp": 1_700_000_000 + i * 3600,
                "open": price * 0.999,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 1000.0 + i,
            }
        )
    return bars


def test_incremental_rsi_macd_atr_match_build_feature_rows():
    bars = _synthetic_bars(80)
    rows = build_feature_rows(bars)
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]

    for i in range(30, len(bars)):
        prefix_c = closes[: i + 1]
        prefix_h = highs[: i + 1]
        prefix_l = lows[: i + 1]
        rsi_v = rsi(prefix_c)[i]
        line, sig, hist = macd(prefix_c)
        atr_v = atr(prefix_h, prefix_l, prefix_c)[i]
        assert rows[i]["rsi_14"] == rsi_v
        assert rows[i]["macd"] == line[i]
        assert rows[i]["macd_signal"] == sig[i]
        assert rows[i]["macd_hist"] == hist[i]
        assert rows[i]["atr_14"] == atr_v


def test_streaming_bollinger_matches_batch_levels():
    closes = [100.0 + 0.5 * math.sin(i / 3.0) for i in range(50)]
    state = bollinger_init(period=20, num_std=2.0)
    streamed: tuple[float, float, float] | None = None
    for c in closes:
        streamed = bollinger_update(state, c)
    batch = bollinger_levels(closes, period=20, num_std=2.0)
    assert streamed is not None
    assert batch is not None
    assert streamed == pytest.approx(batch)


def test_streaming_rolling_mean_matches_window():
    closes = [float(i) for i in range(1, 40)]
    window = 7
    state = rolling_mean_init(window)
    for i, c in enumerate(closes):
        got = rolling_mean_update(state, c)
        if i + 1 >= window:
            expected = sum(closes[i - window + 1 : i + 1]) / window
            assert got == pytest.approx(expected)


def test_streaming_ema_seeds_with_first_close():
    closes = [10.0, 11.0, 9.5, 12.0]
    state = ema_init(3)
    first = ema_update(state, closes[0])
    assert first == closes[0]
