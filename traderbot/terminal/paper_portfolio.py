from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from traderbot.algorithms.base import OrderSize, SignalAction
from traderbot.traders.order_sizing import buy_quote_spend, sell_base_amount
from traderbot.utils.trading_costs import DEFAULT_TRADE_FEE_RATE


def default_paper_initial_cash(dst: str) -> float:
    """Sample wallet size for paper terminal runs."""
    token = dst.strip().lower()
    if token == "usdt":
        return 1_000.0
    return 10_000_000.0


@dataclass
class PaperPortfolio:
    """Simulated quote/base balances for terminal paper mode (full-wallet fills)."""

    quote_cash: float
    quote_currency: str
    base_amount: float = 0.0
    fee_rate: float = DEFAULT_TRADE_FEE_RATE
    #: Market-fill slippage, same convention as the backtest (buys pay more, sells get less).
    slippage_rate: float = 0.0
    session_initial_cash: float | None = None
    last_mark_price: float = 0.0

    def _mark_for_valuation(self, mark_price: float) -> float:
        if mark_price > 0:
            self.last_mark_price = mark_price
            return mark_price
        if self.last_mark_price > 0:
            return self.last_mark_price
        return 0.0

    def equity(self, mark_price: float) -> float:
        mark = self._mark_for_valuation(mark_price)
        if mark <= 0:
            return self.quote_cash
        return self.quote_cash + self.base_amount * mark

    def _initial_cash(self, mark_price: float) -> float:
        if self.session_initial_cash is None:
            self.session_initial_cash = self.equity(mark_price)
        return self.session_initial_cash

    def apply_fill(
        self,
        action: SignalAction,
        price: float,
        *,
        order_size: OrderSize | None = None,
        max_quote_spend: float | None = None,
    ) -> dict[str, Any]:
        if price <= 0:
            return {"filled": False, "reason": "invalid_price"}
        self._mark_for_valuation(price)
        if action == "buy":
            price = price * (1.0 + self.slippage_rate)
        elif action == "sell":
            price = price * (1.0 - self.slippage_rate)
        if action == "buy":
            if self.quote_cash <= 0:
                return {"filled": False, "reason": "no_quote_cash"}
            spend_gross = self.quote_cash
            if order_size is not None:
                spend_gross = buy_quote_spend(
                    order_size,
                    cash=self.quote_cash,
                    position=self.base_amount,
                    fill_price=price,
                    initial_cash=self._initial_cash(price),
                )
                if spend_gross <= 0:
                    return {"filled": False, "reason": "sized_to_zero"}
            if max_quote_spend is not None and max_quote_spend > 0:
                spend_gross = min(spend_gross, max_quote_spend)
            elif max_quote_spend is not None:
                return {"filled": False, "reason": "capital_cap"}
            if spend_gross <= 0:
                return {"filled": False, "reason": "sized_to_zero"}
            spendable = spend_gross / (1.0 + self.fee_rate)
            fee = spend_gross - spendable
            base_bought = spendable / price
            self.base_amount += base_bought
            self.quote_cash -= spend_gross
            return {
                "filled": True,
                "side": "buy",
                "price": price,
                "fee": fee,
                "base_delta": base_bought,
                "quote_spent": spend_gross,
            }
        if action == "sell":
            if self.base_amount <= 0:
                return {"filled": False, "reason": "no_base"}
            base_sold = self.base_amount
            if order_size is not None:
                base_sold = sell_base_amount(
                    order_size,
                    cash=self.quote_cash,
                    position=self.base_amount,
                    fill_price=price,
                )
                if base_sold <= 0:
                    return {"filled": False, "reason": "sized_to_zero"}
            gross = base_sold * price
            fee = gross * self.fee_rate
            quote_received = gross - fee
            self.base_amount -= base_sold
            self.quote_cash += quote_received
            return {
                "filled": True,
                "side": "sell",
                "price": price,
                "fee": fee,
                "base_delta": -base_sold,
                "quote_delta": quote_received,
            }
        return {"filled": False, "reason": "hold"}

    def snapshot(self, mark_price: float) -> dict[str, Any]:
        mark = self._mark_for_valuation(mark_price)
        base_value = self.base_amount * mark if mark > 0 else 0.0
        return {
            "quote_cash": round(self.quote_cash, 8),
            "quote_currency": self.quote_currency,
            "base_amount": round(self.base_amount, 12),
            "base_value": round(base_value, 4),
            "equity": round(self.equity(mark_price), 4),
            "mark_price": mark if mark > 0 else mark_price,
            "mark_kind": "last_closed_bar",
        }
