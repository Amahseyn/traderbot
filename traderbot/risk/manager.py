from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from traderbot.algorithms.base import SignalAction
from traderbot.algorithms.streaming import atr_init, atr_update


@dataclass
class RiskLimits:
    capital_cap: float = 10_000_000.0
    daily_loss_limit_pct: float = 5.0
    max_drawdown_pct: float = 15.0
    volatility_target_pct: float = 2.0
    atr_lookback: int = 14
    kill_switch: bool = False
    stop_loss_pct: float | None = 2.0


@dataclass
class RiskVerdict:
    allowed: bool
    reason: str = ""
    size_multiplier: float = 1.0


@dataclass
class RiskManager:
    limits: RiskLimits
    session_date: date = field(default_factory=date.today)
    day_start_equity: float | None = None
    peak_equity: float | None = None
    last_equity: float | None = None
    halted: bool = False
    halt_reason: str = ""
    _atr: Any = field(default=None)

    def __post_init__(self) -> None:
        if self._atr is None:
            self._atr = atr_init(self.limits.atr_lookback)

    def reset_session(self, equity: float) -> None:
        self.session_date = date.today()
        self.day_start_equity = equity
        self.peak_equity = equity
        self.last_equity = equity
        self.halted = False
        self.halt_reason = ""

    def update_mark(self, equity: float) -> None:
        self.last_equity = equity
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity
        if self.day_start_equity is None:
            self.day_start_equity = equity

    def update_bar_volatility(self, *, high: float, low: float, close: float) -> None:
        atr_update(self._atr, high=high, low=low, close=close)

    def evaluate(
        self,
        action: SignalAction,
        *,
        equity: float,
        mark_price: float,
    ) -> RiskVerdict:
        if self.limits.kill_switch:
            return RiskVerdict(False, "kill_switch")
        if self.halted:
            return RiskVerdict(False, self.halt_reason or "risk_halt")
        self.update_mark(equity)
        if self.day_start_equity and self.day_start_equity > 0:
            day_loss_pct = (equity / self.day_start_equity - 1.0) * 100.0
            if day_loss_pct <= -abs(self.limits.daily_loss_limit_pct):
                self.halted = True
                self.halt_reason = "daily_loss_limit"
                return RiskVerdict(False, self.halt_reason)
        if self.peak_equity and self.peak_equity > 0:
            drawdown_pct = (equity / self.peak_equity - 1.0) * 100.0
            if drawdown_pct <= -abs(self.limits.max_drawdown_pct):
                self.halted = True
                self.halt_reason = "max_drawdown"
                return RiskVerdict(False, self.halt_reason)
        multiplier = 1.0
        atr_value = self._atr.get("atr_value")
        if atr_value and mark_price > 0:
            vol_pct = (atr_value / mark_price) * 100.0
            if vol_pct > 0:
                multiplier = min(1.0, self.limits.volatility_target_pct / vol_pct)
        return RiskVerdict(True, size_multiplier=multiplier)

    def snapshot(self) -> dict[str, Any]:
        return {
            "limits": {
                "capital_cap": self.limits.capital_cap,
                "daily_loss_limit_pct": self.limits.daily_loss_limit_pct,
                "max_drawdown_pct": self.limits.max_drawdown_pct,
                "volatility_target_pct": self.limits.volatility_target_pct,
                "kill_switch": self.limits.kill_switch,
                "stop_loss_pct": self.limits.stop_loss_pct,
            },
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "day_start_equity": self.day_start_equity,
            "peak_equity": self.peak_equity,
            "last_equity": self.last_equity,
        }
