"""Partial fill sizing shared by the backtest engine and live/paper traders."""

from __future__ import annotations

from traderbot.algorithms.base import OrderSize

MIN_ORDER_CASH = 1e-9


def buy_quote_spend(
    size: OrderSize,
    *,
    cash: float,
    position: float,
    fill_price: float,
    initial_cash: float,
) -> float:
    """Quote currency to spend on a buy (0 when the order would be dust)."""
    equity = cash + position * fill_price
    if size.cash_fraction is not None:
        spend = size.cash_fraction * initial_cash
    else:
        spend = float(size.target_exposure) * equity - position * fill_price
    spend = min(spend, cash)
    if spend <= MIN_ORDER_CASH:
        return 0.0
    return spend


def sell_base_amount(
    size: OrderSize,
    *,
    cash: float,
    position: float,
    fill_price: float,
) -> float:
    """Base amount to sell (0 when the order would be dust)."""
    target = float(size.target_exposure or 0.0)
    equity = cash + position * fill_price
    sell_size = min(position, max(0.0, position - target * equity / fill_price))
    if sell_size * fill_price <= MIN_ORDER_CASH:
        return 0.0
    return sell_size
