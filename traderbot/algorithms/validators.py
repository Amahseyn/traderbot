from __future__ import annotations


def validate_fast_slow(fast: int, slow: int) -> None:
    if fast < 1 or slow < 1 or fast >= slow:
        raise ValueError("need 0 < fast < slow")


def validate_rsi_bands(period: int, oversold: float, overbought: float) -> None:
    if period < 2:
        raise ValueError("period must be >= 2")
    if not 0 < oversold < overbought < 100:
        raise ValueError("need 0 < oversold < overbought < 100")


def validate_bollinger(period: int, num_std: float) -> None:
    if period < 2:
        raise ValueError("period must be >= 2")
    if num_std <= 0:
        raise ValueError("num_std must be positive")


def validate_macd(fast: int, slow: int, signal: int) -> None:
    if fast < 1 or slow < 1 or signal < 1 or fast >= slow:
        raise ValueError("need 0 < fast < slow and signal >= 1")


def validate_price_context(
    context_bars: int,
    buy_min_recent_return: float,
    sell_max_recent_return: float,
) -> None:
    if context_bars < 0:
        raise ValueError("context_bars must be >= 0")
    if buy_min_recent_return > sell_max_recent_return:
        raise ValueError("buy_min_recent_return must be <= sell_max_recent_return")
