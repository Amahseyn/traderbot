"""Parity between batch indicators and incremental strategy usage."""

from __future__ import annotations

import math

import pytest

from traderbot.algorithms.bands import bollinger_init, bollinger_update
from traderbot.algorithms.streaming import (
    atr_init,
    atr_update,
    ema_init,
    ema_update,
    macd_init,
    macd_update,
    rolling_mean_init,
    rolling_mean_update,
    rsi_init,
    rsi_update,
)
from traderbot.utils.indicators import atr, macd, rsi


def _synthetic_bars(n = 80) -> list[dict]:
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


def test_incremental_rsi_macd_atr_match_batch():
    bars = _synthetic_bars(80)
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    rsi_state = rsi_init(14)
    macd_state = macd_init(12, 26, 9)
    stream_rsi = None
    stream_line = None
    stream_sig = None
    for close in closes:
        stream_rsi = rsi_update(rsi_state, close)
        stream_line, stream_sig, _stream_hist = macd_update(macd_state, close)

    batch_rsi = rsi(closes)[-1]
    line, sig, _hist = macd(closes)
    atr_v = atr(highs, lows, closes)[-1]
    assert batch_rsi is not None
    assert line[-1] is not None
    assert atr_v is not None
    assert stream_rsi == pytest.approx(batch_rsi)
    assert stream_line == pytest.approx(line[-1])
    assert stream_sig == pytest.approx(sig[-1])


def test_streaming_atr_matches_batch_tail():
    bars = _synthetic_bars(80)
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    state = atr_init(14)
    last_streaming = None
    for bar in bars:
        last_streaming = atr_update(
            state,
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
        )
    batch_tail = atr(highs, lows, closes, period=14)[-1]
    assert last_streaming is not None
    assert batch_tail is not None
    assert last_streaming == pytest.approx(batch_tail)


def test_streaming_sma_ema_bollinger():
    bars = _synthetic_bars(40)
    sma_state = rolling_mean_init(5)
    ema_state = ema_init(5)
    bb_state = bollinger_init(period=20, num_std=2.0)
    for bar in bars:
        close = float(bar["close"])
        rolling_mean_update(sma_state, close)
        ema_update(ema_state, close)
        bollinger_update(bb_state, close)
    assert len(bb_state["buf"]) == 20
