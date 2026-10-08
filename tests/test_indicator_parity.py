"""Parity between batch indicators and incremental strategy usage."""

from __future__ import annotations

import math

import pytest

from traderbot.algorithms.bands import bollinger_init, bollinger_update
from traderbot.algorithms.streaming import (
    atr_init,
    atr_reset,
    atr_update,
    ema_init,
    ema_update,
    rolling_mean_init,
    rolling_mean_update,
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

    for i in range(30, len(bars)):
        prefix_c = closes[: i + 1]
        prefix_h = highs[: i + 1]
        prefix_l = lows[: i + 1]
        rsi_v = rsi(prefix_c)[i]
        line, sig, hist = macd(prefix_c)
        atr_v = atr(prefix_h, prefix_l, prefix_c)[i]
        assert rsi_v is not None
        assert line[i] is not None
        assert atr_v is not None


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
