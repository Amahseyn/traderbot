from __future__ import annotations

import logging

from dataclasses import dataclass

from traderbot.traders.bot_inventory import BotInventory

logger = logging.getLogger(__name__)

_BASE_AMOUNT_TOLERANCE = 1e-10


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    reconciled_down: bool
    surplus_detected: bool
    bot_base: float
    exchange_base: float
    discrepancy: float
    message: str = ""


def audit_and_reconcile_inventory(
    inventory: BotInventory,
    exchange_base: float,
    *,
    mark_price: float,
) -> ReconciliationReport:
    """Audit inventory against exchange holdings and reconcile down when required.

    Surplus exchange balance is never auto-adopted into bot inventory, but is
    flagged as a divergence warning.
    """
    if exchange_base < 0:
        exchange_base = 0.0
    bot_base = inventory.base_amount
    discrepancy = exchange_base - bot_base

    if bot_base > exchange_base + _BASE_AMOUNT_TOLERANCE:
        sold = bot_base - exchange_base
        inventory.record_sell(base_sold=sold)
        logger.info(
            "reconciled bot inventory down by %s base (exchange=%s mark=%s)",
            sold,
            exchange_base,
            mark_price,
        )
        return ReconciliationReport(
            reconciled_down=True,
            surplus_detected=False,
            bot_base=inventory.base_amount,
            exchange_base=exchange_base,
            discrepancy=-sold,
            message=f"Reconciled bot inventory down by {sold} base",
        )

    if discrepancy > _BASE_AMOUNT_TOLERANCE:
        msg = (
            f"Exchange surplus detected: exchange holds {exchange_base} base vs bot {bot_base} "
            f"(surplus of {discrepancy} at mark {mark_price}). Surplus is unadopted."
        )
        logger.warning(msg)
        return ReconciliationReport(
            reconciled_down=False,
            surplus_detected=True,
            bot_base=bot_base,
            exchange_base=exchange_base,
            discrepancy=discrepancy,
            message=msg,
        )

    return ReconciliationReport(
        reconciled_down=False,
        surplus_detected=False,
        bot_base=bot_base,
        exchange_base=exchange_base,
        discrepancy=0.0,
        message="Inventory in sync with exchange",
    )


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
    report = audit_and_reconcile_inventory(inventory, exchange_base, mark_price=mark_price)
    return report.reconciled_down


def base_currency_for_symbol(symbol: str) -> str:
    upper = symbol.strip().upper()
    if upper.endswith("IRT"):
        return upper[:-3].lower()
    if upper.endswith("USDT"):
        return upper[:-4].lower()
    raise ValueError(f"unsupported market symbol: {symbol!r}")
