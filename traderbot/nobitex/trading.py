from __future__ import annotations

from typing import Any

from traderbot.nobitex.client import NobitexClient, NobitexClientError


def _split_symbol(symbol: str) -> tuple[str, str]:
    upper = symbol.strip().upper()
    if upper.endswith("IRT"):
        return upper[:-3].lower(), "rls"
    if upper.endswith("USDT"):
        return upper[:-4].lower(), "usdt"
    raise NobitexClientError(f"unsupported market symbol for orders: {symbol!r}")


def list_wallets(client: NobitexClient) -> dict[str, float]:
    payload = client.request("GET", "/users/wallets/list")
    wallets = payload.get("wallets") if isinstance(payload, dict) else None
    if not isinstance(wallets, list):
        raise NobitexClientError("unexpected wallets response", body=payload)
    balances: dict[str, float] = {}
    for wallet in wallets:
        if not isinstance(wallet, dict):
            continue
        currency = str(wallet.get("currency", "")).lower()
        if not currency:
            continue
        try:
            balances[currency] = float(wallet.get("balance") or 0.0)
        except (TypeError, ValueError):
            balances[currency] = 0.0
    return balances


def add_market_order(
    client: NobitexClient,
    *,
    symbol: str,
    side: str,
    amount: str,
    price: str,
) -> Any:
    src_currency, dst_currency = _split_symbol(symbol)
    body = {
        "type": side,
        "srcCurrency": src_currency,
        "dstCurrency": dst_currency,
        "amount": amount,
        "price": price,
        "execution": "market",
    }
    return client.request("POST", "/market/orders/add", json_body=body)
