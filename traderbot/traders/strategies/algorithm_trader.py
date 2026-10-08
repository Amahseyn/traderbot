from __future__ import annotations

import logging
from collections.abc import Callable

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.nobitex.trading import add_market_order, list_wallets
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
    ):
        super().__init__(client)
        self.algorithm = algorithm
        self.bar_source = bar_source
        self.execution = execution or ExecutionPolicy.paper_only()
        self.market_symbol = market_symbol
        self.in_position = False
        self.algorithm.reset()
        if warmup_bars:
            for warmup_bar in warmup_bars:
                self.algorithm.on_bar(warmup_bar)

    @classmethod
    def from_env(
        cls,
        algorithm: Algorithm,
        *,
        bar_source: BarSource | None = None,
        execution: ExecutionPolicy | None = None,
        market_symbol: str | None = None,
        warmup_bars: list[Bar] | None = None,
    ) -> AlgorithmTrader:
        return cls(
            NobitexClient.from_env(),
            algorithm,
            bar_source=bar_source,
            execution=execution,
            market_symbol=market_symbol,
            warmup_bars=warmup_bars,
        )

    def step(self) -> None:
        bar = self.bar_source() if self.bar_source else None
        if bar is None:
            return
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
        """Place a market order on Nobitex and sync position from wallets when possible."""
        symbol = self.market_symbol or str(bar.get("symbol") or "")
        if not symbol:
            logger.warning("live signal skipped: missing market symbol on bar")
            return
        try:
            self._place_live_order(action, bar, symbol=symbol)
            self._sync_position_from_wallets(symbol)
        except NobitexClientError as exc:
            logger.error("live order failed: %s", exc)

    def _place_live_order(self, action: SignalAction, bar: Bar, *, symbol: str) -> None:
        close_price = float(bar["close"])
        if close_price <= 0:
            raise NobitexClientError("invalid bar close for order pricing")
        price = f"{close_price:.8f}".rstrip("0").rstrip(".")
        if action == "buy":
            balances = list_wallets(self.client)
            dst = "rls" if symbol.upper().endswith("IRT") else "usdt"
            spend = balances.get(dst, 0.0)
            if spend <= 0:
                raise NobitexClientError(f"no {dst} balance for buy")
            amount = f"{spend / close_price:.8f}".rstrip("0").rstrip(".")
            add_market_order(self.client, symbol=symbol, side="buy", amount=amount, price=price)
            return
        if action == "sell":
            balances = list_wallets(self.client)
            src = symbol[:-3].lower() if symbol.upper().endswith("IRT") else symbol[:-4].lower()
            amount = f"{balances.get(src, 0.0):.8f}".rstrip("0").rstrip(".")
            if float(amount or 0) <= 0:
                raise NobitexClientError(f"no {src} balance for sell")
            add_market_order(self.client, symbol=symbol, side="sell", amount=amount, price=price)

    def _sync_position_from_wallets(self, symbol: str) -> None:
        balances = list_wallets(self.client)
        src = symbol[:-3].lower() if symbol.upper().endswith("IRT") else symbol[:-4].lower()
        self.in_position = balances.get(src, 0.0) > 0
