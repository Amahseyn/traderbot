from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

from traderbot.risk.manager import RiskVerdict

logger = logging.getLogger(__name__)


@dataclass
class PortfolioRiskLimits:
    max_aggregate_capital_cap: float = 10_000_000.0
    portfolio_daily_loss_limit_pct: float = 5.0
    portfolio_max_drawdown_pct: float = 15.0
    max_concurrent_positions: int = 5
    max_gross_exposure_equity: float = 1.0
    kill_switch: bool = False


@dataclass
class PortfolioRiskManager:
    limits: PortfolioRiskLimits = field(default_factory=PortfolioRiskLimits)
    session_date: str = field(default="")
    day_start_equity: float | None = None
    peak_equity: float | None = None
    last_equity: float | None = None
    halted: bool = False
    halt_reason: str = ""
    active_positions: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.session_date:
            self.session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def reset_session(self, total_equity: float) -> None:
        self.session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.day_start_equity = total_equity
        self.peak_equity = total_equity
        self.last_equity = total_equity
        self.halted = False
        self.halt_reason = ""

    def _roll_session_if_new_day(self, total_equity: float) -> None:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today_utc == self.session_date:
            return
        self.session_date = today_utc
        self.day_start_equity = total_equity
        if self.halted and self.halt_reason == "portfolio_daily_loss_limit":
            self.halted = False
            self.halt_reason = ""

    def update_mark(self, total_equity: float) -> None:
        self.last_equity = total_equity
        if self.peak_equity is None or total_equity > self.peak_equity:
            self.peak_equity = total_equity
        if self.day_start_equity is None:
            self.day_start_equity = total_equity

    def update_position(self, symbol: str, is_open: bool) -> None:
        if is_open:
            self.active_positions.add(symbol)
        else:
            self.active_positions.discard(symbol)

    def evaluate_entry(
        self,
        symbol: str,
        *,
        requested_notional: float,
        total_equity: float,
        current_gross_notional: float = 0.0,
    ) -> RiskVerdict:
        self._roll_session_if_new_day(total_equity)
        if self.limits.kill_switch:
            return RiskVerdict(False, "portfolio_kill_switch")
        if self.halted:
            return RiskVerdict(False, self.halt_reason or "portfolio_halt")

        self.update_mark(total_equity)

        # Check daily loss limit
        if self.day_start_equity and self.day_start_equity > 0:
            day_loss_pct = (total_equity / self.day_start_equity - 1.0) * 100.0
            if day_loss_pct <= -abs(self.limits.portfolio_daily_loss_limit_pct):
                self.halted = True
                self.halt_reason = "portfolio_daily_loss_limit"
                return RiskVerdict(False, self.halt_reason)

        # Check maximum drawdown limit
        if self.peak_equity and self.peak_equity > 0:
            drawdown_pct = (total_equity / self.peak_equity - 1.0) * 100.0
            if drawdown_pct <= -abs(self.limits.portfolio_max_drawdown_pct):
                self.halted = True
                self.halt_reason = "portfolio_max_drawdown"
                return RiskVerdict(False, self.halt_reason)

        # Check max concurrent positions if this is a new position
        if symbol not in self.active_positions:
            if len(self.active_positions) >= self.limits.max_concurrent_positions:
                return RiskVerdict(
                    False,
                    f"max_concurrent_positions_reached ({len(self.active_positions)}/{self.limits.max_concurrent_positions})",
                )

        # Check max gross exposure vs total equity
        if total_equity > 0 and self.limits.max_gross_exposure_equity > 0:
            projected_gross = current_gross_notional + abs(requested_notional)
            if projected_gross > total_equity * self.limits.max_gross_exposure_equity:
                return RiskVerdict(
                    False,
                    f"max_gross_exposure_exceeded ({projected_gross:.1f} > {total_equity * self.limits.max_gross_exposure_equity:.1f})",
                )

        return RiskVerdict(True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "limits": {
                "max_aggregate_capital_cap": self.limits.max_aggregate_capital_cap,
                "portfolio_daily_loss_limit_pct": self.limits.portfolio_daily_loss_limit_pct,
                "portfolio_max_drawdown_pct": self.limits.portfolio_max_drawdown_pct,
                "max_concurrent_positions": self.limits.max_concurrent_positions,
                "max_gross_exposure_equity": self.limits.max_gross_exposure_equity,
                "kill_switch": self.limits.kill_switch,
            },
            "session_date": self.session_date,
            "day_start_equity": self.day_start_equity,
            "peak_equity": self.peak_equity,
            "last_equity": self.last_equity,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "active_positions": sorted(self.active_positions),
        }

    def restore_from_snapshot(self, data: dict[str, Any]) -> None:
        """Restore state from snapshot, rolling over if a new UTC day has started."""
        if not data:
            return
        saved_date = str(data.get("session_date") or "").strip()
        self.session_date = saved_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.day_start_equity = data.get("day_start_equity")
        self.peak_equity = data.get("peak_equity")
        self.last_equity = data.get("last_equity")
        self.halted = bool(data.get("halted", False))
        self.halt_reason = str(data.get("halt_reason") or "")
        self.active_positions = set(data.get("active_positions", []))

        if self.last_equity is not None:
            self._roll_session_if_new_day(self.last_equity)

    def save_to_file(self, path: Path | str) -> None:
        """Atomically persist portfolio risk state to disk."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f"{target.suffix}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, indent=2)
        os.replace(tmp, target)

    def load_from_file(self, path: Path | str) -> bool:
        """Load persisted portfolio risk state from disk if file exists."""
        target = Path(path)
        if not target.is_file():
            return False
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.restore_from_snapshot(data)
            return True
        except Exception as exc:
            logger.warning("Failed to load portfolio risk state from %s: %s", path, exc)
            return False
