"""Low-timeframe micro-dip scalper with take-profit/stop and session-end flat."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, OrderSpec, SignalAction
from traderbot.algorithms.streaming import atr_init, atr_update

ORDER_MODES = ("legacy", "bracket", "maker")
THRESHOLD_MODES = ("fixed", "atr")

#: Named parameter sets. ``1m`` is the historical default; ``5m`` scales everything to ATR
#: (so it adapts to the slower bar) and uses exchange-side brackets. Both are starting
#: points for walk-forward tuning, not tuned results.
SCALP_DIP_PRESETS: dict[str, dict[str, Any]] = {
    "1m": {
        "dip_lookback_bars": 10,
        "dip_pct": 0.004,
        "take_profit_pct": 0.0075,
        "stop_loss_pct": 0.005,
        "cooldown_bars_after_loss": 3,
    },
    "5m": {
        "dip_lookback_bars": 12,
        "scalp_threshold_mode": "atr",
        "dip_atr_mult": 1.5,
        "tp_atr_mult": 2.0,
        "sl_atr_mult": 1.5,
        "atr_period": 14,
        "cooldown_bars_after_loss": 1,
        "scalp_order_mode": "bracket",
    },
}


class ScalpDipAlgorithm(Algorithm):
    """Buy a micro dip: close at least the dip threshold below the highest close of the last
    ``dip_lookback_bars`` and the bar closes green (bounce confirmation, not a falling knife).

    Thresholds (``scalp_threshold_mode``):

    * ``fixed`` – ``dip_pct`` / ``take_profit_pct`` / ``stop_loss_pct`` as fractions of price.
    * ``atr`` – ``dip_atr_mult`` / ``tp_atr_mult`` / ``sl_atr_mult`` x ATR(``atr_period``),
      frozen at entry, so the scalper adapts to volatility and bar size.

    Execution (``scalp_order_mode``):

    * ``legacy`` – market entry; the strategy itself emits a market exit on the bar after the
      high/low crossed the TP/SL (historical behaviour; exits are measured from the fill).
    * ``bracket`` – market entry with an exchange-side take-profit limit (maker) and stop
      (taker) measured from the actual fill price.
    * ``maker`` – post-only limit entry ``entry_offset_pct`` below the signal close that rests
      ``entry_ttl_bars`` bars, then the same bracket.

    Filters: ``min_volume_ratio`` (bar volume vs. the lookback mean; 0 = off) and
    ``max_spread_pct`` (needs ``spread_pct`` on the bar, e.g. injected from the live book;
    bars without it pass). ``allow_short`` mirrors the setup (pop above the recent low that
    closes red) on perps. Size is always ``scalp_position_fraction`` of equity; after a losing
    trade it waits ``cooldown_bars_after_loss`` bars; flat at ``session_end_hour_utc``.
    """

    name = "scalp_dip"
    uses_position_sizing = True

    def __init__(
        self,
        *,
        dip_lookback_bars=10,
        dip_pct=0.004,
        take_profit_pct=0.0075,
        stop_loss_pct=0.005,
        session_end_hour_utc=-1,
        cooldown_bars_after_loss=3,
        scalp_position_fraction=1.0,
        scalp_threshold_mode: str = "fixed",
        dip_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.0,
        sl_atr_mult: float = 1.5,
        atr_period: int = 14,
        scalp_order_mode: str = "legacy",
        entry_offset_pct: float = 0.0002,
        entry_ttl_bars: int = 2,
        min_volume_ratio: float = 0.0,
        max_spread_pct: float = 0.0,
        allow_short: bool = False,
    ):
        if dip_lookback_bars < 2:
            raise ValueError("dip_lookback_bars must be >= 2")
        if dip_pct <= 0 or take_profit_pct <= 0 or stop_loss_pct <= 0:
            raise ValueError("dip_pct, take_profit_pct and stop_loss_pct must be positive")
        if not -1 <= session_end_hour_utc <= 23:
            raise ValueError("session_end_hour_utc must be -1 or 0..23")
        if cooldown_bars_after_loss < 0:
            raise ValueError("cooldown_bars_after_loss must be >= 0")
        if not 0 < scalp_position_fraction <= 1:
            raise ValueError("scalp_position_fraction must be in (0, 1]")
        if scalp_threshold_mode not in THRESHOLD_MODES:
            raise ValueError(f"scalp_threshold_mode must be one of {THRESHOLD_MODES}")
        if scalp_order_mode not in ORDER_MODES:
            raise ValueError(f"scalp_order_mode must be one of {ORDER_MODES}")
        if dip_atr_mult <= 0 or tp_atr_mult <= 0 or sl_atr_mult <= 0 or atr_period < 1:
            raise ValueError("ATR multipliers must be positive and atr_period >= 1")
        if not 0 <= entry_offset_pct < 0.05 or entry_ttl_bars < 1:
            raise ValueError("entry_offset_pct must be in [0, 0.05) and entry_ttl_bars >= 1")
        if min_volume_ratio < 0 or max_spread_pct < 0:
            raise ValueError("min_volume_ratio and max_spread_pct must be >= 0")
        self.dip_lookback_bars = int(dip_lookback_bars)
        self.dip_pct = dip_pct
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.session_end_hour_utc = session_end_hour_utc
        self.cooldown_bars_after_loss = cooldown_bars_after_loss
        self.scalp_position_fraction = scalp_position_fraction
        self.scalp_threshold_mode = scalp_threshold_mode
        self.dip_atr_mult = dip_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.sl_atr_mult = sl_atr_mult
        self.atr_period = int(atr_period)
        self.scalp_order_mode = scalp_order_mode
        self.entry_offset_pct = entry_offset_pct
        self.entry_ttl_bars = int(entry_ttl_bars)
        self.min_volume_ratio = min_volume_ratio
        self.max_spread_pct = max_spread_pct
        self.allow_short = bool(allow_short)
        self.reset()

    def reset(self) -> None:
        self._closes: deque[float] = deque(maxlen=self.dip_lookback_bars)
        self._volumes: deque[float] = deque(maxlen=self.dip_lookback_bars)
        self._atr = atr_init(self.atr_period)
        self._direction = 0  # +1 long, -1 short, 0 flat (or entry pending)
        self._pending_entry = 0
        self._awaiting_fill = False
        self._entry_price = 0.0
        self._tp = self.take_profit_pct
        self._sl = self.stop_loss_pct
        self._cooldown_bars = 0
        self._size: OrderSize | None = None
        self._spec: OrderSpec | None = None

    @property
    def _in_position(self) -> bool:
        return self._direction != 0

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._direction = 0
            self._pending_entry = 0
        elif self._direction == 0:
            self._direction = 1

    def order_size(self) -> OrderSize | None:
        return self._size

    def order_spec(self) -> OrderSpec | None:
        return self._spec

    def on_fill(self, side: str, price: float, size: float, reason: str, position: float) -> None:
        direction = 0 if position == 0 else (1 if position > 0 else -1)
        if direction != 0:
            if self._awaiting_fill or self._direction != direction or self._entry_price <= 0:
                # TP/SL are measured from the actual fill, not the signal close.
                self._entry_price = price
            self._awaiting_fill = False
            self._direction = direction
            self._pending_entry = 0
            return
        # Flat: bracket/stop or our own exit filled.
        if self._entry_price > 0:
            lost = (price < self._entry_price) if side == "sell" else (price > self._entry_price)
            if reason == "stop_loss" or lost:
                self._cooldown_bars = self.cooldown_bars_after_loss
        self._direction = 0
        self._pending_entry = 0
        self._awaiting_fill = False
        self._entry_price = 0.0

    def on_order_expired(self, side: str) -> None:
        if self._pending_entry:
            self._pending_entry = 0
            self._direction = 0
            self._awaiting_fill = False

    def _session_closing(self, bar: Bar) -> bool:
        if self.session_end_hour_utc < 0:
            return False
        hour = datetime.fromtimestamp(int(bar["timestamp"]), tz=timezone.utc).hour
        return hour == self.session_end_hour_utc

    def _exit(self, lost: bool) -> SignalAction:
        side: SignalAction = "sell" if self._direction > 0 else "buy"
        self._direction = 0
        self._awaiting_fill = False
        self._cooldown_bars = self.cooldown_bars_after_loss if lost else 0
        self._size = OrderSize(target_exposure=0.0)
        self._spec = None if self.scalp_order_mode == "legacy" else OrderSpec(order_type="market")
        return side

    def _thresholds(self, close: float, atr: float | None) -> tuple[float, float, float] | None:
        if self.scalp_threshold_mode == "fixed":
            return self.dip_pct, self.take_profit_pct, self.stop_loss_pct
        if atr is None or atr <= 0 or close <= 0:
            return None
        unit = atr / close
        return self.dip_atr_mult * unit, self.tp_atr_mult * unit, self.sl_atr_mult * unit

    def _filters_pass(self, bar: Bar, prior_volumes: list[float]) -> bool:
        if self.min_volume_ratio > 0 and prior_volumes:
            mean_volume = sum(prior_volumes) / len(prior_volumes)
            if mean_volume > 0 and float(bar.get("volume", 0.0) or 0.0) < self.min_volume_ratio * mean_volume:
                return False
        if self.max_spread_pct > 0:
            spread = bar.get("spread_pct")
            if spread is not None and float(spread) > self.max_spread_pct:
                return False
        return True

    def _enter(self, direction: int, close: float, tp: float, sl: float) -> SignalAction:
        self._tp, self._sl = tp, sl
        self._entry_price = close
        self._awaiting_fill = True
        self._size = OrderSize(target_exposure=direction * self.scalp_position_fraction)
        if self.scalp_order_mode == "legacy":
            self._direction = direction
            self._spec = None
        elif self.scalp_order_mode == "bracket":
            self._direction = direction
            self._spec = OrderSpec(order_type="market", take_profit_pct=tp, stop_loss_pct=sl)
        else:
            self._pending_entry = direction
            limit = close * (1.0 - direction * max(self.entry_offset_pct, 1e-6))
            self._spec = OrderSpec(
                order_type="limit",
                limit_price=limit,
                post_only=True,
                ttl_bars=self.entry_ttl_bars,
                take_profit_pct=tp,
                stop_loss_pct=sl,
            )
        return "buy" if direction > 0 else "sell"

    def on_bar(self, bar: Bar) -> SignalAction:
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        atr = atr_update(self._atr, high=high, low=low, close=close)
        prior_closes = list(self._closes)
        prior_volumes = list(self._volumes)
        self._closes.append(close)
        self._volumes.append(float(bar.get("volume", 0.0) or 0.0))
        self._size = None
        self._spec = None
        session_closing = self._session_closing(bar)

        if self._direction != 0:
            entry = self._entry_price
            long = self._direction > 0
            stop_px = entry * (1 - self._sl) if long else entry * (1 + self._sl)
            tp_px = entry * (1 + self._tp) if long else entry * (1 - self._tp)
            if self.scalp_order_mode == "legacy":
                if (low <= stop_px) if long else (high >= stop_px):
                    return self._exit(lost=True)
                if (high >= tp_px) if long else (low <= tp_px):
                    return self._exit(lost=False)
            else:
                # Brackets normally exit exchange-side; this is a close-based safety net for
                # venues/paths without native brackets.
                if (close <= stop_px) if long else (close >= stop_px):
                    return self._exit(lost=True)
                if (close >= tp_px) if long else (close <= tp_px):
                    return self._exit(lost=False)
            if session_closing:
                return self._exit(lost=(close < entry) if long else (close > entry))
            return "hold"
        if self._pending_entry:
            return "hold"

        if self._cooldown_bars > 0:
            self._cooldown_bars -= 1
            return "hold"
        if session_closing or len(prior_closes) < self.dip_lookback_bars - 1:
            return "hold"
        thresholds = self._thresholds(close, atr)
        if thresholds is None or not self._filters_pass(bar, prior_volumes):
            return "hold"
        dip, tp, sl = thresholds
        if close <= max(prior_closes) * (1 - dip) and close > open_price:
            return self._enter(1, close, tp, sl)
        if self.allow_short and close >= min(prior_closes) * (1 + dip) and close < open_price:
            return self._enter(-1, close, tp, sl)
        return "hold"
