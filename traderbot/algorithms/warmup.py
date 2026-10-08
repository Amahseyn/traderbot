from __future__ import annotations

from typing import Any


def warmup_bar_count(strategy_id: str, kwargs: dict[str, Any]) -> int:
    """Closed bars to feed before the first live or once signal."""
    fast = int(kwargs.get("fast", 5))
    slow = int(kwargs.get("slow", 20))
    signal = int(kwargs.get("signal", 9))
    period = int(kwargs.get("period", 14))
    lookback = int(kwargs.get("lookback_bars", 20))
    atr_period = int(kwargs.get("atr_period", 14))
    swing = int(kwargs.get("swing_window_bars", 3))
    separation = int(kwargs.get("min_swing_separation_bars", 4))

    if strategy_id == "macd_cross":
        return slow + signal + 10
    if strategy_id in ("sma_cross", "ema_cross"):
        return max(fast, slow) + 5
    if strategy_id == "rsi_threshold":
        return period + 5
    if strategy_id == "bollinger_mean_reversion":
        return period + 5
    if strategy_id == "breakout_atr":
        return max(lookback, atr_period) + 5
    if strategy_id == "chart_patterns":
        return 2 * swing + separation + 20
    return max(slow, period, lookback, atr_period) + 10
