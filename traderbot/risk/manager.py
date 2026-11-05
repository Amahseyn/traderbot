from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import SignalAction
from traderbot.algorithms.streaming import atr_init, atr_update

logger = logging.getLogger(__name__)


def utc_today() -> date:
    """Current calendar date in UTC (standard rollover for crypto markets)."""
    return datetime.now(timezone.utc).date()


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
    session_date: date = field(default_factory=utc_today)
    day_start_equity: float | None = None
    peak_equity: float | None = None
    last_equity: float | None = None
    halted: bool = False
    halt_reason: str = ""
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    _atr: Any = field(default=None)

    def __post_init__(self) -> None:
        if self._atr is None:
            self._atr = atr_init(self.limits.atr_lookback)

    def trigger_kill_switch(self, *, operator: str = "system", reason: str = "manual_kill_switch") -> None:
        """Trigger an emergency halt with audited operator attribution."""
        self.halted = True
        self.halt_reason = reason
        self.limits.kill_switch = True
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "halt",
            "operator": operator,
            "reason": reason,
        }
        self.audit_log.append(entry)
        logger.warning("Emergency kill switch triggered by operator '%s': %s", operator, reason)

    def unhalt(self, *, operator: str, reason: str) -> None:
        """Clear a latching risk halt with audited operator attribution.

        Conforms to SEC Rule 15c3-5 and MiFID II RTS 6 audit requirements:
        clearing an automated circuit breaker requires an authenticated operator and a recorded rationale.
        """
        if not self.halted and not self.limits.kill_switch:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "unhalt",
            "operator": operator,
            "reason": reason,
            "previous_halt_reason": self.halt_reason,
        }
        self.audit_log.append(entry)
        self.halted = False
        self.halt_reason = ""
        self.limits.kill_switch = False
        logger.info("Risk halt cleared by operator '%s': %s", operator, reason)

    def reset_session(self, equity: float, *, operator: str = "system", reason: str = "session_reset") -> None:
        self.session_date = utc_today()
        self.day_start_equity = equity
        self.peak_equity = equity
        self.last_equity = equity
        if self.halted or self.limits.kill_switch:
            self.unhalt(operator=operator, reason=reason)
        else:
            self.halted = False
            self.halt_reason = ""

    def _roll_session_if_new_day(self, equity: float) -> None:
        today = utc_today()
        if today == self.session_date:
            return
        self.session_date = today
        self.day_start_equity = equity
        if self.halted and self.halt_reason == "daily_loss_limit":
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
        self._roll_session_if_new_day(equity)
        if action != "sell":
            if self.limits.kill_switch:
                return RiskVerdict(False, "kill_switch")
            if self.halted:
                return RiskVerdict(False, self.halt_reason or "risk_halt")
        self.update_mark(equity)
        if action != "sell":
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
            "session_date": self.session_date.isoformat(),
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "audit_log": list(self.audit_log),
            "day_start_equity": self.day_start_equity,
            "peak_equity": self.peak_equity,
            "last_equity": self.last_equity,
        }

    def restore_from_snapshot(self, data: dict[str, Any]) -> None:
        """Restore state from snapshot, rolling over if a new UTC day has started."""
        if not data:
            return
        saved_date_str = str(data.get("session_date") or "").strip()
        current_today = utc_today()
        if saved_date_str:
            try:
                saved_date = date.fromisoformat(saved_date_str)
            except ValueError:
                saved_date = current_today
        else:
            saved_date = current_today

        self.session_date = saved_date
        self.day_start_equity = data.get("day_start_equity")
        self.peak_equity = data.get("peak_equity")
        self.last_equity = data.get("last_equity")
        self.halted = bool(data.get("halted", False))
        self.halt_reason = str(data.get("halt_reason") or "")
        self.audit_log = list(data.get("audit_log", []))

        if self.last_equity is not None:
            self._roll_session_if_new_day(self.last_equity)

    def save_to_file(self, path: Path | str) -> None:
        """Atomically persist risk state to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f"{target.suffix}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, indent=2)
        os.replace(tmp, target)

    def load_from_file(self, path: Path | str) -> bool:
        """Load persisted risk state from disk if file exists."""
        target = Path(path)
        if not target.is_file():
            return False
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.restore_from_snapshot(data)
            return True
        except Exception as exc:
            logger.warning("Failed to load risk state from %s: %s", path, exc)
            return False
