from __future__ import annotations

from decimal import Decimal, ROUND_DOWN


DEFAULT_MIN_BASE_AMOUNT = 1e-6
DEFAULT_PRICE_DECIMALS = 8
DEFAULT_AMOUNT_DECIMALS = 8
ORDER_FEE_BUFFER = 0.002


def round_price(price: float, *, decimals: int = DEFAULT_PRICE_DECIMALS) -> str:
    if price <= 0:
        raise ValueError("price must be positive")
    quant = Decimal("1").scaleb(-decimals)
    return format(Decimal(str(price)).quantize(quant, rounding=ROUND_DOWN), "f")


def round_amount(amount: float, *, decimals: int = DEFAULT_AMOUNT_DECIMALS) -> str:
    if amount <= 0:
        raise ValueError("amount must be positive")
    quant = Decimal("1").scaleb(-decimals)
    return format(Decimal(str(amount)).quantize(quant, rounding=ROUND_DOWN), "f")


def enforce_min_amount(amount: float, *, min_amount: float = DEFAULT_MIN_BASE_AMOUNT) -> float:
    if amount < min_amount:
        raise ValueError(f"order amount {amount} below minimum {min_amount}")
    return amount


def spendable_quote(quote_balance: float, *, fee_buffer: float = ORDER_FEE_BUFFER) -> float:
    if quote_balance <= 0:
        return 0.0
    return quote_balance / (1.0 + fee_buffer)


def base_from_quote(quote_amount: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return quote_amount / price
