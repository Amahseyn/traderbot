from __future__ import annotations

from typing import Any

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

from traderbot.hyperliquid.credentials import (
    normalize_wallet_address,
    private_key_from_env,
    wallet_address_from_env,
)
from traderbot.hyperliquid.info_client import hyperliquid_info


class HyperliquidTradingError(RuntimeError):
    pass


def hyperliquid_exchange_from_env() -> Exchange:
    private_key = private_key_from_env()
    if not private_key:
        raise HyperliquidTradingError(
            "HYPERLIQUID_PRIVATE_KEY is not set — add it in Lab Settings for live Hyperliquid orders"
        )
    wallet: LocalAccount = eth_account.Account.from_key(private_key)
    address = wallet_address_from_env()
    account_address = normalize_wallet_address(address) if address else None
    if account_address and account_address.lower() != wallet.address.lower():
        return Exchange(wallet, constants.MAINNET_API_URL, account_address=account_address)
    return Exchange(wallet, constants.MAINNET_API_URL)


def hyperliquid_position_size(coin: str) -> float:
    address = wallet_address_from_env()
    if not address:
        raise HyperliquidTradingError("HYPERLIQUID_WALLET_ADDRESS is not set")
    state = hyperliquid_info().user_state(normalize_wallet_address(address))
    for entry in state.get("assetPositions") or []:
        if not isinstance(entry, dict):
            continue
        position = entry.get("position")
        if not isinstance(position, dict):
            continue
        if str(position.get("coin") or "") != coin:
            continue
        try:
            return abs(float(position.get("szi") or 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def hyperliquid_account_value_usd() -> float:
    address = wallet_address_from_env()
    if not address:
        raise HyperliquidTradingError("HYPERLIQUID_WALLET_ADDRESS is not set")
    state = hyperliquid_info().user_state(normalize_wallet_address(address))
    margin = state.get("marginSummary") or {}
    return float(margin.get("accountValue") or 0.0)


def hyperliquid_market_open(coin: str, *, is_buy: bool, size: float, slippage: float = 0.05) -> dict[str, Any]:
    if size <= 0:
        raise HyperliquidTradingError("order size must be positive")
    exchange = hyperliquid_exchange_from_env()
    result = exchange.market_open(coin, is_buy, size, slippage=slippage)
    if isinstance(result, dict) and result.get("status") == "err":
        raise HyperliquidTradingError(str(result.get("response")))
    return result if isinstance(result, dict) else {"response": result}


def hyperliquid_market_close(coin: str, *, size: float | None = None, slippage: float = 0.05) -> dict[str, Any]:
    exchange = hyperliquid_exchange_from_env()
    result = exchange.market_close(coin, sz=size, slippage=slippage)
    if isinstance(result, dict) and result.get("status") == "err":
        raise HyperliquidTradingError(str(result.get("response")))
    return result if isinstance(result, dict) else {"response": result}


def hyperliquid_place_stop(
    coin: str,
    *,
    size: float,
    trigger_price: float,
    slippage: float = 0.05,
) -> dict[str, Any]:
    """Place a reduce-only market stop-loss for an existing long position."""
    if size <= 0:
        raise HyperliquidTradingError("stop size must be positive")
    if trigger_price <= 0:
        raise HyperliquidTradingError("stop trigger price must be positive")
    exchange = hyperliquid_exchange_from_env()
    trigger_px = round(float(trigger_price), 6)
    # Reduce-only market stop-sell: trigger at trigger_px, worst-case fill at a
    # slippage-adjusted limit so the stop can still execute on a fast move.
    limit_px = round(trigger_px * (1.0 - abs(slippage)), 6)
    result = exchange.order(
        coin,
        False,
        size,
        limit_px,
        {"trigger": {"triggerPx": trigger_px, "isMarket": True, "tpsl": "sl"}},
        reduce_only=True,
    )
    if isinstance(result, dict) and result.get("status") == "err":
        raise HyperliquidTradingError(str(result.get("response")))
    return result if isinstance(result, dict) else {"response": result}


def hyperliquid_cancel_order(coin: str, oid: int | str) -> None:
    """Cancel a single open order by exchange order id."""
    exchange = hyperliquid_exchange_from_env()
    result = exchange.cancel(coin, int(oid))
    if isinstance(result, dict) and result.get("status") == "err":
        raise HyperliquidTradingError(str(result.get("response")))


def hyperliquid_order_id(response: dict[str, Any]) -> int | str | None:
    """Extract the exchange order id from an order response, if present."""
    try:
        statuses = response["response"]["data"]["statuses"]
    except (KeyError, TypeError):
        return None
    if not isinstance(statuses, list) or not statuses:
        return None
    first = statuses[0]
    if not isinstance(first, dict):
        return None
    for key in ("resting", "filled", "error"):
        entry = first.get(key)
        if isinstance(entry, dict) and entry.get("oid") is not None:
            return entry.get("oid")
    return None
