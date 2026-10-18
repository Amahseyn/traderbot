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
    fraction of equity (``buy`` raises toward it, ``sell`` trims toward it); negative values
    are short exposure, honoured only where shorts are allowed (Hyperliquid perps).
    ``cash_fraction`` spends that fraction of the backtest's initial cash on a ``buy``
    (fixed-amount orders such as DCA). Without an ``OrderSize`` the engine keeps the
    legacy behavior: full cash on buy, full exit on sell.
    """

    target_exposure: float | None = None
    cash_fraction: float | None = None

    def __post_init__(self) -> None:
        if (self.target_exposure is None) == (self.cash_fraction is None):
            raise ValueError("OrderSize needs exactly one of target_exposure or cash_fraction")
        if self.target_exposure is not None and not -1.0 <= self.target_exposure <= 1.0:
            raise ValueError("target_exposure must be in [-1, 1]")
        if self.cash_fraction is not None and not 0.0 < self.cash_fraction <= 1.0:
            raise ValueError("cash_fraction must be in (0, 1]")


OrderType = Literal["market", "limit"]
FillReason = Literal["market", "limit", "take_profit", "stop_loss", "expired"]


@dataclass(frozen=True, slots=True)
class OrderSpec:
    """How to execute the signal just returned by ``on_bar`` (default: market order).

    * ``limit``: rest a limit at ``limit_price`` for ``ttl_bars`` bars. Backtests fill only
      when a later bar trades **through** the price (buy: ``low < limit``; sell:
      ``high > limit``) at the limit price with the maker fee. ``post_only`` rejects a
      limit that would cross the signal bar's close (it would be a taker fill).
    * ``take_profit_pct`` / ``stop_loss_pct``: bracket placed once the entry fills, measured
      from the **actual fill price**. The take-profit rests as a reduce-only limit (maker);
      the stop is a native stop-market trigger (taker fee + slippage). When both levels sit
      inside one bar the stop is assumed to fill first.
    """

    order_type: OrderType = "market"
    limit_price: float | None = None
    post_only: bool = True
    ttl_bars: int = 1
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None

    def __post_init__(self) -> None:
        if self.order_type not in ("market", "limit"):
            raise ValueError("order_type must be market or limit")
        if self.order_type == "limit" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("limit orders need a positive limit_price")
        if self.ttl_bars < 1:
            raise ValueError("ttl_bars must be >= 1")
        for name in ("take_profit_pct", "stop_loss_pct"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")

    @property
    def has_bracket(self) -> bool:
        return self.take_profit_pct is not None or self.stop_loss_pct is not None


@dataclass(frozen=True, slots=True)
class Quote:
    """One resting maker quote from a quoting strategy (see :meth:`Algorithm.quotes`)."""

    side: Literal["buy", "sell"]
    limit_price: float
    target_exposure: float
    take_profit_pct: float | None = None
    stop_loss_pct: float | None = None


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

    # --- optional execution hooks (backtest engine + live traders) -------------------------

    #: Strategy may open short positions (only honoured on venues that allow shorts).
    allow_short: bool = False

    def order_spec(self) -> OrderSpec | None:
        """Execution for the most recent non-hold signal; ``None`` = market order, no bracket."""
        return None

    @property
    def uses_order_engine(self) -> bool:
        """True when signals need limit/bracket/quote/short execution (paper and live then route
        through the order engine instead of the long-only market path)."""
        return False

    def quotes(self) -> list[Quote] | None:
        """Quoting strategies return the full set of resting maker quotes after each bar.

        ``None`` means the strategy does not quote (signals are used instead). An empty list
        cancels all resting quotes. The engine replaces the previous quotes every bar.
        """
        return None

    def on_fill(self, side: str, price: float, size: float, reason: FillReason, position: float) -> None:
        """Called after an order fills (``position`` = signed base position after the fill)."""

    def on_order_expired(self, side: str) -> None:
        """A limit order expired or was rejected without filling."""
        self.sync_open_position(side == "sell")

    @abstractmethod
    def on_bar(self, bar: Bar) -> SignalAction:
        """Called once per candle, oldest to newest."""
