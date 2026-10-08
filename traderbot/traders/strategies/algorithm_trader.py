from __future__ import annotations

import logging
from collections.abc import Callable

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.markets.order_limits import base_from_quote, spendable_quote
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.nobitex.orders import add_market_order, add_stop_loss_order, wait_for_order_fill
from traderbot.nobitex.trading import list_wallets
from traderbot.risk.runtime import get_risk_manager
from traderbot.traders.bot_inventory import BotInventory
from traderbot.traders.execution import ExecutionPolicy
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
        quote = "rls"
        if market_symbol and market_symbol.upper().endswith("USDT"):
            quote = "usdt"
        cap = capital_cap if capital_cap is not None else get_risk_manager().limits.capital_cap
        self.inventory = inventory or BotInventory(quote_currency=quote, capital_cap=cap)
        self.risk = get_risk_manager()

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

    def step(self) -> None:
        bar = self.bar_source() if self.bar_source else None
        if bar is None:
            return
        self.risk.update_bar_volatility(
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
        )
        signal = self.algorithm.on_bar(bar)
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
            self.in_position = self.inventory.base_amount > 0
            self.last_order_error = None
        except NobitexClientError as exc:
            self.last_order_error = str(exc)
            logger.error("live order failed: %s", exc)
            raise

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
            spendable = spendable_quote(self.inventory.spendable_quote(wallet_quote))
            spendable *= verdict.size_multiplier
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
            sellable = self.inventory.record_sell(base_sold=self.inventory.base_amount)
            if sellable <= 0:
                raise NobitexClientError("bot has no inventory to sell")
            response = add_market_order(
                self.client,
                symbol=symbol,
                side="sell",
                amount=sellable,
                price=close_price,
            )
            order = response.get("order") if isinstance(response, dict) else None
            order_id = order.get("id") if isinstance(order, dict) else None
            if order_id is not None:
                wait_for_order_fill(self.client, order_id)

    def _maybe_place_stop(self, symbol: str, *, base_amount: float, entry_price: float) -> None:
        stop_pct = self.risk.limits.stop_loss_pct
        if stop_pct is None or base_amount <= 0 or entry_price <= 0:
            return
        stop_price = entry_price * (1.0 - abs(stop_pct) / 100.0)
        try:
            add_stop_loss_order(
                self.client,
                symbol=symbol,
                amount=base_amount,
                stop_price=stop_price,
            )
        except NobitexClientError as exc:
            logger.warning("stop order not placed: %s", exc)
