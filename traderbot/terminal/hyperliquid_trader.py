from __future__ import annotations

import logging

from traderbot.algorithms.base import Bar, SignalAction
from traderbot.hyperliquid.market_data import hyperliquid_coin_from_src
from traderbot.hyperliquid.trading import (
    HyperliquidOrderStatus,
    HyperliquidTradingError,
    first_order_status,
    hyperliquid_account_value_usd,
    hyperliquid_cancel_order,
    hyperliquid_market_close,
    hyperliquid_market_open,
    hyperliquid_order_id,
    hyperliquid_place_stop,
    hyperliquid_position_size,
    hyperliquid_sz_decimals,
    prepare_order_size,
)
from traderbot.traders.inventory_reconcile import sync_inventory_to_exchange_base
from traderbot.traders.order_sizing import buy_quote_spend, sell_base_amount
from traderbot.markets.order_limits import base_from_quote
from traderbot.nobitex.client import NobitexClientError
from traderbot.terminal.trader import TerminalAlgorithmTrader

logger = logging.getLogger(__name__)


class HyperliquidTerminalTrader(TerminalAlgorithmTrader):
    """Terminal trader with Hyperliquid perp execution for live mode.

    Equity on perps is the account value (margin + unrealised PnL), so the bot's position is
    **not** added on top of it. Inventory records what the exchange reports as filled
    (``totalSz`` / ``avgPx``), never the requested size or the bar close.
    """

    venue_exchange: str = "hyperliquid"
    hyperliquid_coin: str = "BTC"

    def _coin(self, symbol: str | None = None) -> str:
        return self.hyperliquid_coin or hyperliquid_coin_from_src(symbol or self.market_symbol or "")

    def _sz_decimals(self, coin: str) -> int:
        cache = getattr(self, "_sz_decimals_cache", None)
        if cache is None:
            cache = {}
            self._sz_decimals_cache = cache
        if coin not in cache:
            cache[coin] = hyperliquid_sz_decimals(coin)
        return cache[coin]

    def _reconcile_inventory_from_exchange(self, bar: Bar) -> None:
        close_price = float(bar["close"])
        if close_price <= 0:
            return
        coin = self._coin()
        try:
            exchange_base = hyperliquid_position_size(coin)
        except HyperliquidTradingError as exc:
            logger.debug("hyperliquid inventory reconcile skipped: %s", exc)
            return
        if sync_inventory_to_exchange_base(
            self.inventory,
            max(0.0, exchange_base),
            mark_price=close_price,
        ):
            self.in_position = self.inventory.base_amount > 0
            if not self.in_position:
                # Position closed off-bot (stop / take-profit filled): drop sibling orders.
                self._cancel_active_stop(coin)

    def perp_equity(self, account_value: float) -> float:
        """Perp equity = account value (already includes the position's unrealised PnL)."""
        return float(account_value)

    def _free_quote(self, account_value: float, mark_price: float) -> float:
        """Account value not already committed to the bot's open position (1x notional)."""
        return max(0.0, float(account_value) - self.inventory.base_amount * mark_price)

    def _fill_from_response(self, response, *, requested: float, coin: str) -> HyperliquidOrderStatus:
        try:
            status = first_order_status(response)
        except HyperliquidTradingError as exc:
            raise NobitexClientError(str(exc)) from exc
        if status.status == "filled" and status.filled_size > 0:
            return status
        raise NobitexClientError(
            f"Hyperliquid {coin} order not filled (status={status.status}, requested={requested})"
        )

    def _place_live_order(self, action: SignalAction, bar: Bar, *, symbol: str) -> None:
        close_price = float(bar["close"])
        if close_price <= 0:
            raise NobitexClientError("invalid bar close for order pricing")
        coin = self._coin(symbol)
        try:
            account_value = hyperliquid_account_value_usd()
        except HyperliquidTradingError as exc:
            raise NobitexClientError(str(exc)) from exc
        equity = self.perp_equity(account_value)
        free_quote = self._free_quote(account_value, close_price)
        verdict = self.risk.evaluate(action, equity=equity, mark_price=close_price)
        if not verdict.allowed:
            raise NobitexClientError(f"risk blocked order: {verdict.reason}")

        if action == "buy":
            spendable = self.inventory.spendable_quote(free_quote)
            spendable *= verdict.size_multiplier
            if self._pending_order_size is not None:
                sized_spend = buy_quote_spend(
                    self._pending_order_size,
                    cash=free_quote,
                    position=self.inventory.base_amount,
                    fill_price=close_price,
                    initial_cash=self._initial_cash_for_sizing(equity=equity),
                )
                spendable = min(spendable, sized_spend)
            if spendable <= 0:
                raise NobitexClientError("no USDC margin within bot capital cap")
            try:
                size = prepare_order_size(
                    coin,
                    float(base_from_quote(spendable, close_price)),
                    price=close_price,
                    sz_decimals=self._sz_decimals(coin),
                )
                response = hyperliquid_market_open(coin, is_buy=True, size=size)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            fill = self._fill_from_response(response, requested=size, coin=coin)
            self.inventory.record_buy(
                quote_spent=fill.filled_size * fill.avg_price,
                base_received=fill.filled_size,
                price=fill.avg_price,
            )
            self.last_fill_price = fill.avg_price
            self._maybe_place_stop(coin, base_amount=fill.filled_size, entry_price=fill.avg_price)
            return

        if action == "sell":
            sellable = self.inventory.base_amount
            if self._pending_order_size is not None:
                sized = sell_base_amount(
                    self._pending_order_size,
                    cash=free_quote,
                    position=sellable,
                    fill_price=close_price,
                )
                if sized > 0:
                    sellable = sized
            if sellable <= 0:
                raise NobitexClientError("bot has no inventory to sell")
            decimals = self._sz_decimals(coin)
            try:
                size = prepare_order_size(coin, sellable, price=close_price, reduce_only=True, sz_decimals=decimals)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            self._cancel_active_stop(coin)
            try:
                response = hyperliquid_market_close(coin, size=size)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            fill = self._fill_from_response(response, requested=size, coin=coin)
            # Rounding dust below one lot cannot be sold: drop it from bot inventory too.
            sold = fill.filled_size
            if self.inventory.base_amount - sold < 10 ** (-decimals):
                sold = self.inventory.base_amount
            self.inventory.record_sell(base_sold=sold)
            self.last_fill_price = fill.avg_price
            return

    def _cancel_active_stop(self, coin: str) -> None:
        for attr in ("active_stop_order_id", "active_take_profit_order_id"):
            order_id = getattr(self, attr, None)
            if order_id is None:
                continue
            try:
                hyperliquid_cancel_order(coin, order_id)
            except (HyperliquidTradingError, ValueError) as exc:
                logger.warning("failed to cancel Hyperliquid order %s on %s: %s", order_id, coin, exc)
            finally:
                setattr(self, attr, None)

    def _maybe_place_stop(self, coin: str, *, base_amount: float, entry_price: float) -> None:
        stop_pct = self.risk.limits.stop_loss_pct
        if stop_pct is None or base_amount <= 0 or entry_price <= 0:
            return
        self._cancel_active_stop(coin)
        stop_price = entry_price * (1.0 - abs(stop_pct) / 100.0)
        try:
            response = hyperliquid_place_stop(
                coin,
                size=base_amount,
                trigger_price=stop_price,
                sz_decimals=self._sz_decimals(coin),
            )
        except HyperliquidTradingError as exc:
            raise NobitexClientError(f"protective stop not placed: {exc}") from exc
        self.active_stop_order_id = hyperliquid_order_id(response)
        if self.active_stop_order_id is None:
            logger.warning("Hyperliquid stop placed for %s but no order id was returned", coin)
