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
    client_order_id: str | None = None,
) -> Any:
    from traderbot.nobitex.orders import add_market_order as place_market_order

    return place_market_order(
        client,
        symbol=symbol,
        side=side,
        amount=float(amount),
        price=float(price),
        client_order_id=client_order_id,
    )
