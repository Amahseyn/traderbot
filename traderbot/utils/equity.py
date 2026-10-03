from __future__ import annotations


def buy_hold_value(
    initial: float,
    start_price: float | None,
    current_price: float | None,
) -> float:
    if start_price is None or current_price is None or start_price <= 0:
        return initial
    return initial * (current_price / start_price)


def final_equity_from_curve(curve: list[float], *, default = 100.0) -> float:
    return curve[-1] if curve else default
