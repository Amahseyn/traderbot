from __future__ import annotations

import logging
from collections.abc import Callable

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction
from traderbot.traders.order_sizing import buy_quote_spend, sell_base_amount
from traderbot.markets.order_limits import base_from_quote
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.nobitex.orders import (
    add_market_order,
    add_stop_loss_order,
    cancel_open_order,
    order_id_from_response,
    wait_for_order_fill,
)
from traderbot.nobitex.trading import list_wallets
from traderbot.risk.runtime import get_risk_manager
from traderbot.traders.bot_inventory import BotInventory
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.inventory_reconcile import base_currency_for_symbol, sync_inventory_to_exchange_base
from traderbot.traders.nobitex import NobitexTrader
from traderbot.traders.position import order_action_for_long_only

BarSource = Callable[[], Bar | None]

logger = logging.getLogger(__name__)


class AlgorithmTrader(NobitexTrader):
    """
    Runs an :class:`~traderbot.algorithms.base.Algorithm` each ``step``.

    Provide ``bar_source`` (latest candle) and override :meth:`on_signal` for order placement.
    Backtests use the same algorithm class via :func:`traderbot.backtesting.run_backtest`.
    """

    name = "algorithm"
    venue_exchange: str = "nobitex"

    def __init__(
        self,
        client,
        algorithm: Algorithm,
        *,
        bar_source: BarSource | None = None,
        execution: ExecutionPolicy | None = None,
        market_symbol: str | None = None,
        warmup_bars: list[Bar] | None = None,
        capital_cap: float | None = None,
        inventory: BotInventory | None = None,
        risk_scope: str | None = None,
        risk_manager=None,
    ):
        super().__init__(client)
        self.algorithm = algorithm
        self.bar_source = bar_source
        self.execution = execution or ExecutionPolicy.paper_only()
        self.market_symbol = market_symbol
        self.in_position = False
        self.last_order_error: str | None = None
        self.algorithm.reset()
        if warmup_bars:
            for warmup_bar in warmup_bars:
                self.algorithm.on_bar(warmup_bar)
        self.algorithm.sync_open_position(self.in_position)
        quote = "rls"
        if market_symbol and market_symbol.upper().endswith("USDT"):
            quote = "usdt"
        scope = risk_scope or market_symbol or "default"
        self.risk_scope = scope
        self.risk = risk_manager if risk_manager is not None else get_risk_manager(scope)
        cap = capital_cap if capital_cap is not None else self.risk.limits.capital_cap
        self.inventory = inventory or BotInventory(quote_currency=quote, capital_cap=cap)
        self.active_stop_order_id: int | str | None = None
        self._pending_order_size: OrderSize | None = None
        self._session_initial_cash: float | None = None

    @classmethod
    def from_env(
        cls,
        algorithm: Algorithm,
        *,
        bar_source: BarSource | None = None,
        execution: ExecutionPolicy | None = None,
        market_symbol: str | None = None,
        warmup_bars: list[Bar] | None = None,
        capital_cap: float | None = None,
    ) -> AlgorithmTrader:
        return cls(
            NobitexClient.from_env(),
            algorithm,
            bar_source=bar_source,
            execution=execution,
            market_symbol=market_symbol,
            warmup_bars=warmup_bars,
            capital_cap=capital_cap,
        )

    def prepare_for_bar(self, bar: Bar) -> None:
        if self.execution.mode == "live" and self.market_symbol:
            self._reconcile_inventory_from_exchange(bar)
        self.risk.update_bar_volatility(
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
        )
        if getattr(self.algorithm, "uses_order_engine", False):
            # The order engine reports fills via on_fill; only align once after warmup so a
            # resting (unfilled) limit entry is not wiped every bar.
            if not getattr(self, "_order_engine_synced", False):
                self._order_engine_synced = True
                self.algorithm.sync_open_position(self.in_position)
            return
        self.algorithm.sync_open_position(self.in_position)

    def step(self) -> None:
        bar = self.bar_source() if self.bar_source else None
        if bar is None:
            return
        self.prepare_for_bar(bar)
        signal = self.algorithm.on_bar(bar)
        self._pending_order_size = self.algorithm.order_size() if signal != "hold" else None
        order_action = order_action_for_long_only(self.in_position, signal)
        if order_action is None:
            return
        if not self.execution.permits(order_action):
            return
        if self.execution.mode == "paper":
            self.on_paper_signal(order_action, bar)
            self._apply_position_after_fill(order_action)
        else:
            self.on_signal(order_action, bar)

    def _apply_position_after_fill(self, action: SignalAction) -> None:
        if action == "buy":
            self.in_position = True
        elif action == "sell":
            self.in_position = False

    def _initial_cash_for_sizing(self, *, equity: float) -> float:
        if self._session_initial_cash is None:
            self._session_initial_cash = equity if equity > 0 else self.inventory.capital_cap
        return self._session_initial_cash

    def _sync_in_position_from_holdings(self) -> None:
        self.in_position = self.inventory.base_amount > 0

    def on_paper_signal(self, action: SignalAction, bar: Bar) -> None:
        """Hook for logging or sim fills when :attr:`execution` is paper mode."""

    def on_signal(self, action: SignalAction, bar: Bar) -> None:
        """Place a market order on Nobitex and sync position from bot inventory."""
        symbol = self.market_symbol or str(bar.get("symbol") or "")
        if not symbol:
            self.last_order_error = "missing market symbol on bar"
            logger.warning("live signal skipped: %s", self.last_order_error)
            return
        try:
            self._place_live_order(action, bar, symbol=symbol)
            self._sync_in_position_from_holdings()
            self.last_order_error = None
        except NobitexClientError as exc:
            self.last_order_error = str(exc)
            self.algorithm.sync_open_position(self.in_position)
            logger.error("live order failed: %s", exc)
            raise

    def _reconcile_inventory_from_exchange(self, bar: Bar) -> None:
        symbol = self.market_symbol or str(bar.get("symbol") or "")
        if not symbol:
            return
        try:
            close_price = float(bar["close"])
            balances = list_wallets(self.client)
            base = base_currency_for_symbol(symbol)
            exchange_base = balances.get(base, 0.0)
            if sync_inventory_to_exchange_base(
                self.inventory,
                exchange_base,
                mark_price=close_price,
            ):
                self.in_position = self.inventory.base_amount > 0
        except (NobitexClientError, ValueError) as exc:
            logger.debug("inventory reconcile skipped: %s", exc)

    def _quote_currency(self, symbol: str) -> str:
        return "usdt" if symbol.upper().endswith("USDT") else "rls"

    def _base_currency(self, symbol: str) -> str:
        upper = symbol.upper()
        if upper.endswith("IRT"):
            return upper[:-3].lower()
        if upper.endswith("USDT"):
            return upper[:-4].lower()
        raise NobitexClientError(f"unsupported market symbol for orders: {symbol!r}")

    def _place_live_order(self, action: SignalAction, bar: Bar, *, symbol: str) -> None:
        close_price = float(bar["close"])
        if close_price <= 0:
            raise NobitexClientError("invalid bar close for order pricing")
        balances = list_wallets(self.client)
        quote = self._quote_currency(symbol)
        wallet_quote = balances.get(quote, 0.0)
        equity = wallet_quote + self.inventory.base_amount * close_price
        verdict = self.risk.evaluate(action, equity=equity, mark_price=close_price)
        if not verdict.allowed:
            raise NobitexClientError(f"risk blocked order: {verdict.reason}")

        if action == "buy":
            spendable = self.inventory.spendable_quote(wallet_quote)
            spendable *= verdict.size_multiplier
            if self._pending_order_size is not None:
                quote_cash = wallet_quote
                position_value = self.inventory.base_amount * close_price
                sized_spend = buy_quote_spend(
                    self._pending_order_size,
                    cash=quote_cash,
                    position=self.inventory.base_amount,
                    fill_price=close_price,
                    initial_cash=self._initial_cash_for_sizing(equity=equity),
                )
                spendable = min(spendable, sized_spend)
            if spendable <= 0:
                raise NobitexClientError(f"no {quote} balance within bot capital cap")
            amount = base_from_quote(spendable, close_price)
            response = add_market_order(
                self.client,
                symbol=symbol,
                side="buy",
                amount=amount,
                price=close_price,
            )
            order = response.get("order") if isinstance(response, dict) else None
            order_id = order.get("id") if isinstance(order, dict) else None
            filled = wait_for_order_fill(self.client, order_id) if order_id is not None else order
            matched = float(filled.get("matchedAmount") or amount) if isinstance(filled, dict) else amount
            self.inventory.record_buy(quote_spent=spendable, base_received=matched, price=close_price)
            self._maybe_place_stop(symbol, base_amount=matched, entry_price=close_price)
            return

        if action == "sell":
            sellable = self.inventory.base_amount
            if self._pending_order_size is not None:
                quote_cash = wallet_quote
                sized = sell_base_amount(
                    self._pending_order_size,
                    cash=quote_cash,
                    position=sellable,
                    fill_price=close_price,
                )
                if sized > 0:
                    sellable = sized
            if sellable <= 0:
                raise NobitexClientError("bot has no inventory to sell")
            self._cancel_active_stop(symbol)
            response = add_market_order(
                self.client,
                symbol=symbol,
                side="sell",
                amount=sellable,
                price=close_price,
            )
            order = response.get("order") if isinstance(response, dict) else None
            order_id = order.get("id") if isinstance(order, dict) else None
            filled = (
                wait_for_order_fill(self.client, order_id)
                if order_id is not None
                else order
            )
            matched = float(filled.get("matchedAmount") or sellable) if isinstance(filled, dict) else sellable
            self.inventory.record_sell(base_sold=matched)

    def _cancel_active_stop(self, symbol: str) -> None:
        if self.active_stop_order_id is None:
            return
        order_id = self.active_stop_order_id
        try:
            cancel_open_order(self.client, order_id)
        except NobitexClientError as exc:
            logger.warning("failed to cancel stop order %s on %s: %s", order_id, symbol, exc)
        finally:
            self.active_stop_order_id = None

    def _maybe_place_stop(self, symbol: str, *, base_amount: float, entry_price: float) -> None:
        stop_pct = self.risk.limits.stop_loss_pct
        if stop_pct is None or base_amount <= 0 or entry_price <= 0:
            return
        self._cancel_active_stop(symbol)
        stop_price = entry_price * (1.0 - abs(stop_pct) / 100.0)
        try:
            response = add_stop_loss_order(
                self.client,
                symbol=symbol,
                amount=base_amount,
                stop_price=stop_price,
            )
        except NobitexClientError as exc:
            raise NobitexClientError(f"protective stop not placed: {exc}") from exc
        self.active_stop_order_id = order_id_from_response(response)
