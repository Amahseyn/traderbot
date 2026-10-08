from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BotInventory:
    """Tracks coins the bot bought (not the full exchange wallet)."""

    quote_currency: str
    capital_cap: float
    quote_reserved: float = 0.0
    base_amount: float = 0.0
    avg_entry_price: float = 0.0

    def spendable_quote(self, wallet_quote: float) -> float:
        cap = min(self.capital_cap, wallet_quote)
        return max(0.0, cap - self.quote_reserved)

    def record_buy(self, *, quote_spent: float, base_received: float, price: float) -> None:
        self.quote_reserved += quote_spent
        if base_received > 0:
            total_cost = self.avg_entry_price * self.base_amount + price * base_received
            self.base_amount += base_received
            self.avg_entry_price = total_cost / self.base_amount if self.base_amount > 0 else 0.0

    def record_sell(self, *, base_sold: float) -> float:
        sold = min(base_sold, self.base_amount)
        self.base_amount -= sold
        if self.base_amount <= 0:
            self.avg_entry_price = 0.0
        return sold

    def snapshot(self) -> dict[str, float | str]:
        return {
            "quote_currency": self.quote_currency,
            "capital_cap": self.capital_cap,
            "quote_reserved": round(self.quote_reserved, 8),
            "base_amount": round(self.base_amount, 12),
            "avg_entry_price": round(self.avg_entry_price, 8),
        }
