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


def validate_cost_edge(min_edge_over_cost: float | None, roundtrip_cost_pct: float | None) -> None:
    if min_edge_over_cost is not None and min_edge_over_cost < 0:
        raise ValueError("min_edge_over_cost must be None or >= 0 (0 disables the gate)")
    if roundtrip_cost_pct is not None and not 0 <= roundtrip_cost_pct < 1:
        raise ValueError("roundtrip_cost_pct must be None or in [0, 1)")


ENTRY_ORDER_MODES = ("market", "maker")


def validate_entry_execution(entry_order_mode: str, entry_offset_pct: float, entry_ttl_bars: int) -> None:
    if entry_order_mode not in ENTRY_ORDER_MODES:
        raise ValueError(f"entry_order_mode must be one of {ENTRY_ORDER_MODES}")
    if not 0 <= entry_offset_pct < 0.05:
        raise ValueError("entry_offset_pct must be in [0, 0.05)")
    if entry_ttl_bars < 1:
        raise ValueError("entry_ttl_bars must be >= 1")
