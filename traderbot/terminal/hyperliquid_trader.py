from __future__ import annotations

import logging

from traderbot.algorithms.base import Bar, SignalAction
from traderbot.hyperliquid.market_data import hyperliquid_coin_from_src
from traderbot.hyperliquid.trading import (
    HyperliquidTradingError,
    hyperliquid_account_value_usd,
    hyperliquid_market_close,
    hyperliquid_market_open,
    hyperliquid_position_size,
)
from traderbot.traders.inventory_reconcile import sync_inventory_to_exchange_base
from traderbot.markets.order_limits import base_from_quote, spendable_quote
from traderbot.nobitex.client import NobitexClientError
from traderbot.terminal.trader import TerminalAlgorithmTrader

logger = logging.getLogger(__name__)


class HyperliquidTerminalTrader(TerminalAlgorithmTrader):
    """Terminal trader with Hyperliquid perp execution for live mode."""

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
            spendable = spendable_quote(self.inventory.spendable_quote(wallet_equity))
            spendable *= verdict.size_multiplier
            if spendable <= 0:
                raise NobitexClientError("no USDC margin within bot capital cap")
            size = float(base_from_quote(spendable, close_price))
            try:
                hyperliquid_market_open(coin, is_buy=True, size=size)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            self.inventory.record_buy(quote_spent=spendable, base_received=size, price=close_price)
            return

        if action == "sell":
            sellable = self.inventory.base_amount
            if sellable <= 0:
                raise NobitexClientError("bot has no inventory to sell")
            try:
                hyperliquid_market_close(coin, size=sellable)
            except HyperliquidTradingError as exc:
                raise NobitexClientError(str(exc)) from exc
            self.inventory.record_sell(base_sold=sellable)
            return
