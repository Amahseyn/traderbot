"""Hyperliquid perp order helpers (signed exchange calls).

Everything here that sends an order needs ``HYPERLIQUID_PRIVATE_KEY``; nothing in the test
suite reaches the network (callers are monkeypatched).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from traderbot.hyperliquid.credentials import (
    normalize_wallet_address,
    private_key_from_env,
    wallet_address_from_env,
)
from traderbot.hyperliquid.info_client import hyperliquid_info

# Hyperliquid rejects orders below $10 notional (reduce-only closes are exempt).
HYPERLIQUID_MIN_ORDER_NOTIONAL_USD = 10.0
# Hyperliquid prices: at most 5 significant figures and (6 - szDecimals) decimals on perps.
_MAX_SIG_FIGS = 5
_PERP_MAX_PRICE_DECIMALS = 6
DEFAULT_MARKET_SLIPPAGE = 0.05


class HyperliquidTradingError(RuntimeError):
    pass


# --- session-scoped clients -------------------------------------------------------------

_exchange_lock = threading.Lock()
_exchange_cache: dict[tuple[str, str | None], Any] = {}


def hyperliquid_exchange_from_env(*, refresh: bool = False):
    """One signed ``Exchange`` per wallet for the process (constructing one fetches meta)."""
    private_key = private_key_from_env()
    if not private_key:
        raise HyperliquidTradingError(
            "HYPERLIQUID_PRIVATE_KEY is not set — add it in Lab Settings for live Hyperliquid orders"
        )
    import eth_account
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants

    wallet = eth_account.Account.from_key(private_key)
    address = wallet_address_from_env()
    account_address = normalize_wallet_address(address) if address else None
    if account_address and account_address.lower() == wallet.address.lower():
        account_address = None
    key = (wallet.address.lower(), account_address.lower() if account_address else None)
    with _exchange_lock:
        if refresh or key not in _exchange_cache:
            if account_address:
                _exchange_cache[key] = Exchange(wallet, constants.MAINNET_API_URL, account_address=account_address)
            else:
                _exchange_cache[key] = Exchange(wallet, constants.MAINNET_API_URL)
        return _exchange_cache[key]


def reset_hyperliquid_exchange_cache() -> None:
    with _exchange_lock:
        _exchange_cache.clear()
    _asset_meta_cache.clear()


# --- market metadata / rounding ---------------------------------------------------------

_asset_meta_cache: dict[str, dict[str, Any]] = {}


def hyperliquid_asset_meta(coin: str) -> dict[str, Any]:
    """Perp universe entry for ``coin`` (``szDecimals``, ``maxLeverage``, ...), cached."""
    name = coin.strip().upper()
    if name not in _asset_meta_cache:
        meta = hyperliquid_info().meta()
        for entry in meta.get("universe") or []:
            if isinstance(entry, dict) and entry.get("name"):
                _asset_meta_cache[str(entry["name"]).upper()] = entry
    entry = _asset_meta_cache.get(name)
    if entry is None:
        raise HyperliquidTradingError(f"unknown Hyperliquid perp {coin!r}")
    return entry


def hyperliquid_sz_decimals(coin: str) -> int:
    return int(hyperliquid_asset_meta(coin).get("szDecimals", 0))


def round_hyperliquid_size(size: float, sz_decimals: int) -> float:
    """Floor ``size`` to the coin's lot size (never round up into more than intended)."""
    if size <= 0:
        return 0.0
    quant = Decimal(1).scaleb(-int(sz_decimals))
    return float(Decimal(str(size)).quantize(quant, rounding=ROUND_FLOOR))


def round_hyperliquid_price(
    price: float,
    sz_decimals: int,
    *,
    round_up: bool = False,
    is_spot: bool = False,
) -> float:
    """Valid Hyperliquid tick: ≤5 significant figures and ≤(6|8 − szDecimals) decimals.

    ``round_up=False`` rounds toward a less aggressive buy (down); use ``round_up=True`` for
    sell limits so a maker quote never crosses into a taker fill by rounding.
    """
    if price <= 0:
        raise HyperliquidTradingError("price must be positive")
    rounding = ROUND_CEILING if round_up else ROUND_FLOOR
    value = Decimal(str(price))
    max_decimals = (8 if is_spot else _PERP_MAX_PRICE_DECIMALS) - int(sz_decimals)
    if value >= 1 and value == value.to_integral_value():
        return float(value)  # integer prices are always valid
    exponent = value.adjusted()  # position of the leading digit
    sig_quant = Decimal(1).scaleb(exponent - _MAX_SIG_FIGS + 1)
    value = value.quantize(sig_quant, rounding=rounding)
    dec_quant = Decimal(1).scaleb(-max(0, max_decimals))
    if value.as_tuple().exponent < -max(0, max_decimals):
        value = value.quantize(dec_quant, rounding=rounding)
    return float(value)


def prepare_order_size(
    coin: str,
    size: float,
    *,
    price: float,
    reduce_only: bool = False,
    sz_decimals: int | None = None,
) -> float:
    """Round to lot size and enforce the $10 minimum notional (opening orders only)."""
    decimals = hyperliquid_sz_decimals(coin) if sz_decimals is None else int(sz_decimals)
    rounded = round_hyperliquid_size(size, decimals)
    if rounded <= 0:
        raise HyperliquidTradingError(f"order size {size} rounds to 0 at {decimals} size decimals for {coin}")
    if not reduce_only and rounded * price < HYPERLIQUID_MIN_ORDER_NOTIONAL_USD:
        raise HyperliquidTradingError(
            f"order notional {rounded * price:.2f} USD is below Hyperliquid's "
            f"{HYPERLIQUID_MIN_ORDER_NOTIONAL_USD:.0f} USD minimum"
        )
    return rounded


# --- response parsing -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HyperliquidOrderStatus:
    """One entry of ``response.data.statuses`` (or an ``orderStatus`` query)."""

    status: str  # "filled" | "resting" | "error" | "open" | "canceled" | ...
    oid: int | str | None = None
    filled_size: float = 0.0
    avg_price: float = 0.0
    error: str | None = None

    @property
    def is_filled(self) -> bool:
        return self.filled_size > 0


def parse_order_statuses(response: Any) -> list[HyperliquidOrderStatus]:
    """All per-order statuses. Raises on a top-level ``err`` or an unrecognised payload."""
    if not isinstance(response, dict):
        raise HyperliquidTradingError(f"unexpected Hyperliquid order response: {response!r}")
    if response.get("status") == "err":
        raise HyperliquidTradingError(str(response.get("response")))
    try:
        statuses = response["response"]["data"]["statuses"]
    except (KeyError, TypeError) as exc:
        raise HyperliquidTradingError(f"Hyperliquid order response has no statuses: {response!r}") from exc
    if not isinstance(statuses, list) or not statuses:
        raise HyperliquidTradingError(f"Hyperliquid order response has no statuses: {response!r}")
    parsed: list[HyperliquidOrderStatus] = []
    for entry in statuses:
        if isinstance(entry, str):  # e.g. "success" for cancels / "waitingForFill"
            parsed.append(HyperliquidOrderStatus(status=entry))
            continue
        if not isinstance(entry, dict):
            parsed.append(HyperliquidOrderStatus(status="error", error=repr(entry)))
            continue
        if "error" in entry:
            parsed.append(HyperliquidOrderStatus(status="error", error=str(entry["error"])))
        elif isinstance(entry.get("filled"), dict):
            filled = entry["filled"]
            parsed.append(
                HyperliquidOrderStatus(
                    status="filled",
                    oid=filled.get("oid"),
                    filled_size=float(filled.get("totalSz") or 0.0),
                    avg_price=float(filled.get("avgPx") or 0.0),
                )
            )
        elif isinstance(entry.get("resting"), dict):
            parsed.append(HyperliquidOrderStatus(status="resting", oid=entry["resting"].get("oid")))
        else:
            parsed.append(HyperliquidOrderStatus(status="error", error=f"unrecognised status {entry!r}"))
    return parsed


def first_order_status(response: Any) -> HyperliquidOrderStatus:
    """First status; raises :class:`HyperliquidTradingError` when the order was rejected."""
    status = parse_order_statuses(response)[0]
    if status.status == "error":
        raise HyperliquidTradingError(f"order rejected: {status.error}")
    return status


def hyperliquid_order_id(response: dict[str, Any]) -> int | str | None:
    """Extract the exchange order id from an order response, if present."""
    try:
        statuses = parse_order_statuses(response)
    except HyperliquidTradingError:
        return None
    for status in statuses:
        if status.oid is not None:
            return status.oid
    return None


# --- account reads (public info endpoint, keyed by wallet address) ----------------------


def _wallet_address() -> str:
    address = wallet_address_from_env()
    if not address:
        raise HyperliquidTradingError("HYPERLIQUID_WALLET_ADDRESS is not set")
    return normalize_wallet_address(address)


def hyperliquid_position_size(coin: str) -> float:
    """Signed position size (``szi``): positive long, negative short, 0 flat."""
    state = hyperliquid_info().user_state(_wallet_address())
    for entry in state.get("assetPositions") or []:
        if not isinstance(entry, dict):
            continue
        position = entry.get("position")
        if not isinstance(position, dict):
            continue
        if str(position.get("coin") or "") != coin:
            continue
        try:
            return float(position.get("szi") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def hyperliquid_account_value_usd() -> float:
    """Perp account value: margin balance **including** unrealised PnL of open positions."""
    state = hyperliquid_info().user_state(_wallet_address())
    margin = state.get("marginSummary") or {}
    return float(margin.get("accountValue") or 0.0)


def hyperliquid_order_status(oid: int | str) -> HyperliquidOrderStatus:
    """Current state of one order: ``open`` / ``filled`` / ``canceled`` with filled size so far."""
    payload = hyperliquid_info().query_order_by_oid(_wallet_address(), int(oid))
    if not isinstance(payload, dict) or payload.get("status") != "order":
        return HyperliquidOrderStatus(status="unknown", oid=oid)
    wrapper = payload.get("order") or {}
    order = wrapper.get("order") or {}
    orig = float(order.get("origSz") or 0.0)
    remaining = float(order.get("sz") or 0.0)
    return HyperliquidOrderStatus(
        status=str(wrapper.get("status") or "unknown"),
        oid=order.get("oid", oid),
        filled_size=max(0.0, orig - remaining),
        avg_price=float(order.get("limitPx") or 0.0),
    )


def hyperliquid_best_bid_ask(coin: str) -> tuple[float, float]:
    """Top of book from the public L2 snapshot."""
    book = hyperliquid_info().l2_snapshot(coin)
    levels = book.get("levels") if isinstance(book, dict) else None
    if not levels or len(levels) < 2 or not levels[0] or not levels[1]:
        raise HyperliquidTradingError(f"empty Hyperliquid book for {coin}")
    return float(levels[0][0]["px"]), float(levels[1][0]["px"])


# --- orders -------------------------------------------------------------------------------


def hyperliquid_market_open(
    coin: str,
    *,
    is_buy: bool,
    size: float,
    slippage: float = DEFAULT_MARKET_SLIPPAGE,
) -> dict[str, Any]:
    """Aggressive IOC open; raises when the exchange rejects the order (top-level or per order)."""
    if size <= 0:
        raise HyperliquidTradingError("order size must be positive")
    exchange = hyperliquid_exchange_from_env()
    result = exchange.market_open(coin, is_buy, size, slippage=slippage)
    first_order_status(result)
    return result


def hyperliquid_market_close(
    coin: str,
    *,
    size: float | None = None,
    slippage: float = DEFAULT_MARKET_SLIPPAGE,
) -> dict[str, Any]:
    exchange = hyperliquid_exchange_from_env()
    result = exchange.market_close(coin, sz=size, slippage=slippage)
    if result is None:
        raise HyperliquidTradingError(f"no open {coin} position to close")
    first_order_status(result)
    return result


def hyperliquid_limit_order(
    coin: str,
    *,
    is_buy: bool,
    size: float,
    price: float,
    post_only: bool = True,
    reduce_only: bool = False,
) -> dict[str, Any]:
    """Resting limit order. ``post_only`` uses ALO so it is never a taker fill (maker fee)."""
    if size <= 0:
        raise HyperliquidTradingError("order size must be positive")
    exchange = hyperliquid_exchange_from_env()
    tif = "Alo" if post_only else "Gtc"
    result = exchange.order(coin, is_buy, size, price, {"limit": {"tif": tif}}, reduce_only=reduce_only)
    first_order_status(result)
    return result


def hyperliquid_place_stop(
    coin: str,
    *,
    size: float,
    trigger_price: float,
    slippage: float = DEFAULT_MARKET_SLIPPAGE,
    is_buy: bool = False,
    sz_decimals: int | None = None,
) -> dict[str, Any]:
    """Reduce-only native stop-market trigger (sell for longs; ``is_buy=True`` covers a short)."""
    if size <= 0:
        raise HyperliquidTradingError("stop size must be positive")
    if trigger_price <= 0:
        raise HyperliquidTradingError("stop trigger price must be positive")
    decimals = hyperliquid_sz_decimals(coin) if sz_decimals is None else int(sz_decimals)
    exchange = hyperliquid_exchange_from_env()
    # Round the trigger away from the position (never tighter than requested).
    trigger_px = round_hyperliquid_price(trigger_price, decimals, round_up=is_buy)
    # Worst-case fill limit so the stop still executes on a fast move.
    raw_limit = trigger_px * (1.0 + abs(slippage)) if is_buy else trigger_px * (1.0 - abs(slippage))
    limit_px = round_hyperliquid_price(raw_limit, decimals, round_up=is_buy)
    result = exchange.order(
        coin,
        is_buy,
        size,
        limit_px,
        {"trigger": {"triggerPx": trigger_px, "isMarket": True, "tpsl": "sl"}},
        reduce_only=True,
    )
    first_order_status(result)
    return result


def hyperliquid_cancel_order(coin: str, oid: int | str) -> None:
    """Cancel a single open order by exchange order id."""
    exchange = hyperliquid_exchange_from_env()
    result = exchange.cancel(coin, int(oid))
    if isinstance(result, dict) and result.get("status") == "err":
        raise HyperliquidTradingError(str(result.get("response")))
    try:
        statuses = parse_order_statuses(result)
    except HyperliquidTradingError:
        return
    for status in statuses:
        if status.status == "error":
            raise HyperliquidTradingError(f"cancel rejected: {status.error}")
