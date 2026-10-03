from __future__ import annotations


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
