from __future__ import annotations

import time
import uuid
from typing import Any

from traderbot.markets.order_limits import enforce_min_amount, round_amount, round_price
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.nobitex.trading import _split_symbol


def new_client_order_id() -> str:
    return f"tb-{uuid.uuid4().hex[:24]}"


def add_market_order(
    client: NobitexClient,
    *,
    symbol: str,
    side: str,
    amount: float,
    price: float,
    client_order_id: str | None = None,
) -> Any:
    src_currency, dst_currency = _split_symbol(symbol)
    amount_text = round_amount(enforce_min_amount(amount))
    price_text = round_price(price)
    body = {
        "type": side,
        "srcCurrency": src_currency,
        "dstCurrency": dst_currency,
        "amount": amount_text,
        "price": price_text,
        "execution": "market",
        "clientOrderId": client_order_id or new_client_order_id(),
    }
    return client.request("POST", "/market/orders/add", json_body=body)


def fetch_order_status(client: NobitexClient, order_id: int | str) -> dict[str, Any]:
    payload = client.request("GET", "/market/orders/status", params={"id": order_id})
    order = payload.get("order") if isinstance(payload, dict) else None
    if not isinstance(order, dict):
        raise NobitexClientError("unexpected order status response", body=payload)
    return order


def wait_for_order_fill(
    client: NobitexClient,
    order_id: int | str,
    *,
    poll_interval_sec: float = 1.0,
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = fetch_order_status(client, order_id)
        status = str(last.get("status", "")).lower()
        if status in ("done", "filled"):
            return last
        if status in ("canceled", "cancelled", "rejected"):
            raise NobitexClientError(f"order {order_id} ended with status {status}", body=last)
        time.sleep(poll_interval_sec)
    raise NobitexClientError(f"order {order_id} not filled within {timeout_sec}s", body=last)


def add_stop_loss_order(
    client: NobitexClient,
    *,
    symbol: str,
    amount: float,
    stop_price: float,
    client_order_id: str | None = None,
) -> Any:
    src_currency, dst_currency = _split_symbol(symbol)
    body = {
        "type": "sell",
        "srcCurrency": src_currency,
        "dstCurrency": dst_currency,
        "amount": round_amount(enforce_min_amount(amount)),
        "price": round_price(stop_price),
        "execution": "stop_limit",
        "clientOrderId": client_order_id or new_client_order_id(),
    }
    return client.request("POST", "/market/orders/add", json_body=body)
