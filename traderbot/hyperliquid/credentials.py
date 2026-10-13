from __future__ import annotations

import os
import re

WALLET_ADDRESS_ENV = "HYPERLIQUID_WALLET_ADDRESS"
PRIVATE_KEY_ENV = "HYPERLIQUID_PRIVATE_KEY"

_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


def normalize_wallet_address(address: str) -> str:
    cleaned = address.strip()
    if not _ADDRESS_PATTERN.match(cleaned):
        raise ValueError("Hyperliquid wallet must be a 0x-prefixed 20-byte address")
    return cleaned


def wallet_address_from_env() -> str | None:
    raw = os.environ.get(WALLET_ADDRESS_ENV, "").strip()
    if not raw:
        return None
    return normalize_wallet_address(raw)


def private_key_from_env() -> str | None:
    raw = os.environ.get(PRIVATE_KEY_ENV, "").strip()
    return raw or None


def hyperliquid_wallet_configured() -> bool:
    try:
        return wallet_address_from_env() is not None
    except ValueError:
        return False


def hyperliquid_trading_configured() -> bool:
    return hyperliquid_wallet_configured() and bool(private_key_from_env())
