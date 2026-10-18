from __future__ import annotations

import logging

from traderbot.algorithms.base import Bar, SignalAction
from traderbot.hyperliquid.market_data import hyperliquid_coin_from_src
from traderbot.hyperliquid.trading import (
    HyperliquidTradingError,
    hyperliquid_account_value_usd,
    hyperliquid_cancel_order,
    hyperliquid_market_close,
    hyperliquid_market_open,
    hyperliquid_order_id,
    hyperliquid_place_stop,
    hyperliquid_position_size,
)
from traderbot.traders.inventory_reconcile import sync_inventory_to_exchange_base
from traderbot.traders.order_sizing import buy_quote_spend, sell_base_amount
from traderbot.markets.order_limits import base_from_quote
from traderbot.nobitex.client import NobitexClientError
from traderbot.terminal.trader import TerminalAlgorithmTrader

logger = logging.getLogger(__name__)


class HyperliquidTerminalTrader(TerminalAlgorithmTrader):
    """Terminal trader with Hyperliquid perp execution for live mode."""

    venue_exchange: str = "hyperliquid"
    hyperliquid_coin: str = "BTC"

    def _reconcile_inventory_from_exchange(self, bar: Bar) -> None:
        close_price = float(bar["close"])
        if close_price <= 0:
            return
        coin = self.hyperliquid_coin or hyperliquid_coin_from_src(self.market_symbol or "")
        try:
            exchange_base = hyperliquid_position_size(coin)
        except HyperliquidTradingError as exc:
            logger.debug("hyperliquid inventory reconcile skipped: %s", exc)
            return
        if sync_inventory_to_exchange_base(
            self.inventory,
            exchange_base,
            mark_price=close_price,
        ):
            self.in_position = self.inventory.base_amount > 0

    def _place_live_order(self, action: SignalAction, bar: Bar, *, symbol: str) -> None:
        close_price = float(bar["close"])
        if close_price <= 0:
            raise NobitexClientError("invalid bar close for order pricing")
        coin = self.hyperliquid_coin or hyperliquid_coin_from_src(symbol)
        try:
            wallet_equity = hyperliquid_account_value_usd()
        except HyperliquidTradingError as exc:
            raise NobitexClientError(str(exc)) from exc
        equity = wallet_equity + self.inventory.base_amount * close_price
        verdict = self.risk.evaluate(action, equity=equity, mark_price=close_price)
        if not verdict.allowed:
            raise NobitexClientError(f"risk blocked order: {verdict.reason}")

        if action == "buy":
            spendable = self.inventory.spendable_quote(wallet_equity)
            spendable *= verdict.size_multiplier
            if self._pending_order_size is not None:
                sized_spend = buy_quote_spend(
                    self._pending_order_size,
                    cash=wallet_equity,
                    position=self.inventory.base_amount,
                    fill_price=close_price,
                    initial_cash=self._initial_cash_for_sizing(equity=equity),
                )
                spendable = min(spendable, sized_spend)
            if spendable <= 0:
                raise NobitexClientError("no USDC margin within bot capital cap")
            size = float(base_from_quote(spendable, close_price))
            try:
                hyperliquid_market_open(coin, is_buy=True, size=size)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            self.inventory.record_buy(quote_spent=spendable, base_received=size, price=close_price)
            self._maybe_place_stop(coin, base_amount=size, entry_price=close_price)
            return

        if action == "sell":
            sellable = self.inventory.base_amount
            if self._pending_order_size is not None:
                sized = sell_base_amount(
                    self._pending_order_size,
                    cash=wallet_equity,
                    position=sellable,
                    fill_price=close_price,
                )
                if sized > 0:
                    sellable = sized
            if sellable <= 0:
                raise NobitexClientError("bot has no inventory to sell")
            self._cancel_active_stop(coin)
            try:
                hyperliquid_market_close(coin, size=sellable)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            self.inventory.record_sell(base_sold=sellable)
            return

    def _cancel_active_stop(self, coin: str) -> None:
        if self.active_stop_order_id is None:
            return
        order_id = self.active_stop_order_id
        try:
            hyperliquid_cancel_order(coin, order_id)
        except (HyperliquidTradingError, ValueError) as exc:
            logger.warning("failed to cancel Hyperliquid stop %s on %s: %s", order_id, coin, exc)
        finally:
            self.active_stop_order_id = None

    def _maybe_place_stop(self, coin: str, *, base_amount: float, entry_price: float) -> None:
        stop_pct = self.risk.limits.stop_loss_pct
        if stop_pct is None or base_amount <= 0 or entry_price <= 0:
            return
        self._cancel_active_stop(coin)
        stop_price = entry_price * (1.0 - abs(stop_pct) / 100.0)
        try:
            response = hyperliquid_place_stop(coin, size=base_amount, trigger_price=stop_price)
        except HyperliquidTradingError as exc:
            raise NobitexClientError(f"protective stop not placed: {exc}") from exc
        self.active_stop_order_id = hyperliquid_order_id(response)
        if self.active_stop_order_id is None:
            logger.warning("Hyperliquid stop placed for %s but no order id was returned", coin)
