"""Shared entry execution for the threshold strategies.

Signal-driven strategies default to market entries, which pay the taker fee plus slippage on
both legs (0.190% per roundtrip on Hyperliquid perp, 0.900% on Nobitex). A post-only limit at
``entry_offset_pct`` below the signal close fills as **maker** (0.015% fee, no slippage) or not
at all, which is the cheaper side of the same trade. :class:`MakerEntry` keeps that choice in
one place so ``sma_cross``, ``ema_cross``, ``rsi_threshold``, ``macd_cross`` and
``bollinger_mean_reversion`` all expose the same ``entry_order_mode`` knob.

Exits stay market orders: a mean-reversion or trend exit that never fills leaves the position
open, which is a larger risk than the exit fee it saves.
"""

from __future__ import annotations

from traderbot.algorithms.base import OrderSpec, SignalAction
from traderbot.algorithms.validators import ENTRY_ORDER_MODES, validate_entry_execution


class MakerEntry:
    """Post-only limit entry state for one strategy instance.

    ``entry_side`` names which signal opens risk. For the long-only threshold strategies that
    is ``buy``: a ``sell`` closes the position and must stay a market order, because an exit
    that never fills leaves the position (and its risk) open.
    """

    __slots__ = ("entry_offset_pct", "entry_order_mode", "entry_side", "entry_ttl_bars")

    def __init__(
        self,
        *,
        entry_order_mode: str = "market",
        entry_offset_pct: float = 0.0002,
        entry_ttl_bars: int = 2,
        entry_side: str = "buy",
    ) -> None:
        validate_entry_execution(entry_order_mode, entry_offset_pct, entry_ttl_bars)
        if entry_side not in ("buy", "sell"):
            raise ValueError("entry_side must be 'buy' or 'sell'")
        self.entry_order_mode = entry_order_mode
        self.entry_offset_pct = float(entry_offset_pct)
        self.entry_ttl_bars = int(entry_ttl_bars)
        self.entry_side = entry_side

    @property
    def is_maker(self) -> bool:
        return self.entry_order_mode == "maker"

    @property
    def modes(self) -> tuple[str, ...]:
        return ENTRY_ORDER_MODES

    def limit_price(self, action: SignalAction, close: float) -> float:
        """Rest below the close for a buy and above it for a sell (never crossing)."""
        offset = max(self.entry_offset_pct, 1e-6)
        if action == "buy":
            return close * (1.0 - offset)
        if action == "sell":
            return close * (1.0 + offset)
        return close

    def spec_for(self, action: SignalAction, close: float) -> OrderSpec | None:
        """``None`` keeps the default market fill; a limit spec rests for ``entry_ttl_bars``."""
        if not self.is_maker or action == "hold" or close <= 0 or action != self.entry_side:
            return None
        return OrderSpec(
            order_type="limit",
            limit_price=self.limit_price(action, close),
            post_only=True,
            ttl_bars=self.entry_ttl_bars,
        )
