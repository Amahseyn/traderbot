from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

SignalAction = Literal["buy", "sell", "hold"]

# Same keys as :func:`traderbot.markets.market_data.ohlc_rows` and export CSV rows.
Bar = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class OrderSize:
    """Optional sizing for the signal just returned by ``on_bar``.

    Exactly one field is set. ``target_exposure`` is the desired position value as a
    fraction of equity (``buy`` raises toward it, ``sell`` trims toward it).
    ``cash_fraction`` spends that fraction of the backtest's initial cash on a ``buy``
    (fixed-amount orders such as DCA). Without an ``OrderSize`` the engine keeps the
    legacy behavior: full cash on buy, full exit on sell.
    """

    target_exposure: float | None = None
    cash_fraction: float | None = None

    def __post_init__(self) -> None:
        if (self.target_exposure is None) == (self.cash_fraction is None):
            raise ValueError("OrderSize needs exactly one of target_exposure or cash_fraction")
        if self.target_exposure is not None and not 0.0 <= self.target_exposure <= 1.0:
            raise ValueError("target_exposure must be in [0, 1]")
        if self.cash_fraction is not None and not 0.0 < self.cash_fraction <= 1.0:
            raise ValueError("cash_fraction must be in (0, 1]")


class Algorithm(ABC):
    """Pure strategy logic: one bar in, one signal out. Shared by live traders and backtests."""

    name = "algorithm"
    # True when ``order_size`` returns partial sizes (vectorbt all-in metrics would not match).
    uses_position_sizing = False

    def reset(self) -> None:
        """Clear state before a new backtest run or bot session."""

    def order_size(self) -> OrderSize | None:
        """Sizing for the most recent non-hold signal; ``None`` = all-in / all-out.

        Only the backtest engine honors partial sizes; live traders treat every
        ``buy``/``sell`` as a full entry/exit.
        """
        return None

    def sync_open_position(self, in_position: bool) -> None:
        """Align internal flags when live inventory diverges from strategy state."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> SignalAction:
        """Called once per candle, oldest to newest."""
