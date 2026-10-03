from __future__ import annotations

import math
from typing import Any

from traderbot.ml.utils import INTRAHOUR_BAR_KEYS as INTRAHOUR_FEATURE_KEYS

_NUMERIC = ("open", "high", "low", "close", "volume")

INTRAHOUR_BAR_KEYS = INTRAHOUR_FEATURE_KEYS


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def rsi(closes: list[float], period = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def macd(
    closes: list[float],
    fast = 12,
    slow = 26,
    signal = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("macd periods must be >= 1")
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    line: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if i < slow - 1:
            continue
        line[i] = ema_fast[i] - ema_slow[i]
    valid_line = [x if x is not None else 0.0 for x in line]
    sig = _ema(valid_line, signal)
    hist: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if line[i] is None:
            continue
        hist[i] = line[i] - sig[i]
    signal_out: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if line[i] is None:
            continue
        signal_out[i] = sig[i]
    return line, signal_out, hist


def atr(highs: list[float], lows: list[float], closes: list[float], period = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(closes)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    trs: list[float] = []
    for i in range(n):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            trs.append(tr)
    if n < period:
        return out
    atr_val = sum(trs[:period]) / period
    out[period - 1] = atr_val
    for i in range(period, n):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        out[i] = atr_val
    return out


def build_feature_rows(
    bars: list[dict[str, Any]],
    *,
    intrahour_features: list[dict[str, float | None]] | None = None,
) -> list[dict[str, Any]]:
    """
    Per-bar feature dict aligned with ``bars`` (same length).

    Uses OHLCV plus RSI, MACD, ATR, and simple returns. Optional keys such as
    ``funding_rate`` or ``open_interest`` on the bar are passed through when present.
    ``intrahour_features`` (1m-derived, any coarse resolution) are merged when supplied.
    """
    if not bars:
        return []
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    volumes = [float(b.get("volume") or 0.0) for b in bars]
    rsi_v = rsi(closes)
    macd_line, macd_sig, macd_hist = macd(closes)
    atr_v = atr(highs, lows, closes)

    rows: list[dict[str, Any]] = []
    for i, bar in enumerate(bars):
        close = closes[i]
        prev = closes[i - 1] if i else close
        ret_1 = (close / prev - 1.0) if prev else 0.0
        row: dict[str, Any] = {
            "timestamp": int(bar["timestamp"]),
            "open": float(bar["open"]),
            "high": highs[i],
            "low": lows[i],
            "close": close,
            "volume": volumes[i],
            "return_1": ret_1,
            "rsi_14": rsi_v[i],
            "macd": macd_line[i],
            "macd_signal": macd_sig[i],
            "macd_hist": macd_hist[i],
            "atr_14": atr_v[i],
        }
        for key in ("funding_rate", "open_interest", "volume_delta", "market_breadth"):
            if key in bar and bar[key] not in (None, ""):
                row[key] = float(bar[key])
        if intrahour_features is not None:
            ih = intrahour_features[i]
            for key, val in ih.items():
                if val is not None:
                    row[key] = val
        for key in INTRAHOUR_BAR_KEYS:
            if key in bar and bar[key] not in (None, ""):
                row[key] = float(bar[key])
        rows.append(row)
    return rows


def forward_log_return(closes: list[float], horizon_bars: int) -> list[float | None]:
    """log(close[t+h]/close[t]) for each t; trailing ``horizon_bars`` entries are None."""
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    n = len(closes)
    out: list[float | None] = [None] * n
    for i in range(n - horizon_bars):
        c0, c1 = closes[i], closes[i + horizon_bars]
        if c0 <= 0 or c1 <= 0:
            continue
        out[i] = math.log(c1 / c0)
    return out
