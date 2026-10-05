from __future__ import annotations


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def rsi(closes: list[float], period = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for bar_index in range(1, period + 1):
        delta = closes[bar_index] - closes[bar_index - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for bar_index in range(period + 1, len(closes)):
        delta = closes[bar_index] - closes[bar_index - 1]
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[bar_index] = 100.0
        else:
            out[bar_index] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
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
    for bar_index in range(len(closes)):
        if bar_index < slow - 1:
            continue
        line[bar_index] = ema_fast[bar_index] - ema_slow[bar_index]
    valid_line = [value if value is not None else 0.0 for value in line]
    signal_series = _ema(valid_line, signal)
    histogram: list[float | None] = [None] * len(closes)
    signal_out: list[float | None] = [None] * len(closes)
    for bar_index in range(len(closes)):
        if line[bar_index] is None:
            continue
        histogram[bar_index] = line[bar_index] - signal_series[bar_index]
        signal_out[bar_index] = signal_series[bar_index]
    return line, signal_out, histogram


def atr(highs: list[float], lows: list[float], closes: list[float], period = 14) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    bar_count = len(closes)
    out: list[float | None] = [None] * bar_count
    if bar_count == 0:
        return out
    true_ranges: list[float] = []
    for bar_index in range(bar_count):
        if bar_index == 0:
            true_ranges.append(highs[bar_index] - lows[bar_index])
        else:
            true_range = max(
                highs[bar_index] - lows[bar_index],
                abs(highs[bar_index] - closes[bar_index - 1]),
                abs(lows[bar_index] - closes[bar_index - 1]),
            )
            true_ranges.append(true_range)
    if bar_count < period:
        return out
    atr_value = sum(true_ranges[:period]) / period
    out[period - 1] = atr_value
    for bar_index in range(period, bar_count):
        atr_value = (atr_value * (period - 1) + true_ranges[bar_index]) / period
        out[bar_index] = atr_value
    return out
