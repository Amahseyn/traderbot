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
