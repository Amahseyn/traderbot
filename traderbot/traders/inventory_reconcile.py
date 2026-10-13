from __future__ import annotations

import logging

from traderbot.traders.bot_inventory import BotInventory

logger = logging.getLogger(__name__)

_BASE_AMOUNT_TOLERANCE = 1e-10


def sync_inventory_to_exchange_base(
    inventory: BotInventory,
    exchange_base: float,
    *,
    mark_price: float,
) -> bool:
    """
    Align bot inventory downward when the exchange holds less base than tracked.

    Typical cause: a protective stop or external sell filled without updating ``BotInventory``.
    Does not adopt surplus exchange balance (pre-existing holdings stay outside bot inventory).
    """
    if exchange_base < 0:
        exchange_base = 0.0
    if inventory.base_amount <= exchange_base + _BASE_AMOUNT_TOLERANCE:
        return False
    sold = inventory.base_amount - exchange_base
    inventory.record_sell(base_sold=sold)
    logger.info(
        "reconciled bot inventory down by %s base (exchange=%s mark=%s)",
        sold,
        exchange_base,
        mark_price,
    )
    return True


def base_currency_for_symbol(symbol: str) -> str:
    upper = symbol.strip().upper()
    if upper.endswith("IRT"):
        return upper[:-3].lower()
    if upper.endswith("USDT"):
        return upper[:-4].lower()
    raise ValueError(f"unsupported market symbol: {symbol!r}")
