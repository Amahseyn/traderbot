from __future__ import annotations


def return_pct_over_equity_tail(
    equity_curve: list[tuple[int, float]],
    holdout_tail_bars: int,
) -> float | None:
    """Simple return from equity just before the tail window through the last bar."""
    if holdout_tail_bars < 1:
        raise ValueError("holdout_tail_bars must be >= 1")
    bar_count = len(equity_curve)
    if bar_count < holdout_tail_bars + 1:
        return None
    start_index = bar_count - holdout_tail_bars
    start_equity = equity_curve[start_index - 1][1]
    end_equity = equity_curve[-1][1]
    if start_equity <= 0:
        return None
    return (end_equity / start_equity - 1.0) * 100.0
