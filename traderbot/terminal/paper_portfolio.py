from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from traderbot.algorithms.base import SignalAction
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

    def equity(self, mark_price: float) -> float:
        if mark_price <= 0:
            return self.quote_cash
        return self.quote_cash + self.base_amount * mark_price

    def apply_fill(self, action: SignalAction, price: float) -> dict[str, Any]:
        if price <= 0:
            return {"filled": False, "reason": "invalid_price"}
        if action == "buy":
            if self.quote_cash <= 0:
                return {"filled": False, "reason": "no_quote_cash"}
            spendable = self.quote_cash / (1.0 + self.fee_rate)
            fee = self.quote_cash - spendable
            base_bought = spendable / price
            self.base_amount += base_bought
            self.quote_cash = 0.0
            return {
                "filled": True,
                "side": "buy",
                "price": price,
                "fee": fee,
                "base_delta": base_bought,
            }
        if action == "sell":
            if self.base_amount <= 0:
                return {"filled": False, "reason": "no_base"}
            gross = self.base_amount * price
            fee = gross * self.fee_rate
            quote_received = gross - fee
            base_sold = self.base_amount
            self.base_amount = 0.0
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
        return {
            "quote_cash": round(self.quote_cash, 8),
            "quote_currency": self.quote_currency,
            "base_amount": round(self.base_amount, 12),
            "equity": round(self.equity(mark_price), 4),
            "mark_price": mark_price,
        }
