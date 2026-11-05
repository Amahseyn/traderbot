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
    pair_limits: Any = None  # PairRiskLimits | None


@dataclass
class RiskVerdict:
    allowed: bool
    reason: str = ""
    size_multiplier: float = 1.0


from traderbot.risk.pair_models import (  # noqa: E402
    PairExposureInfo,
    PairRiskLimits,
    PairRiskState,
    StatArbRiskVerdict,
)


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
    pair_states: dict[str, PairRiskState] = field(default_factory=dict)
    pair_emergency_exits: set[str] = field(default_factory=set)

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

    def evaluate_pair_limits(
        self,
        pair_state: PairRiskState,
        total_equity: float,
    ) -> StatArbRiskVerdict:
        """
        Evaluate pair-specific constraints:
        1. Max allocation per pair.
        2. Max gross pair exposure.
        3. Max net exposure.
        4. Max leverage.
        5. Max hedge deviation.
        6. Max holding duration.
        7. Max pair loss.
        8. Max spread divergence.
        """
        limits = self.limits.pair_limits or PairRiskLimits()
        gross = pair_state.gross_notional
        net = pair_state.net_notional
        dev = pair_state.hedge_deviation_pct
        lev = pair_state.effective_leverage
        loss_pct = pair_state.pair_loss_pct
        z_score = pair_state.current_z_score
        holding = pair_state.holding_bars

        exposure_info = PairExposureInfo(
            pair_id=pair_state.pair_id,
            symbol_a=pair_state.symbol_a,
            symbol_b=pair_state.symbol_b,
            leg_a_qty=pair_state.leg_a_qty,
            leg_b_qty=pair_state.leg_b_qty,
            leg_a_notional=pair_state.leg_a_notional,
            leg_b_notional=pair_state.leg_b_notional,
            gross_notional=gross,
            net_notional=net,
            leverage=lev,
            hedge_deviation_pct=dev,
            holding_duration_bars=holding,
            current_spread=pair_state.current_spread,
            spread_z_score=z_score,
        )

        # 1. Max allocation per pair
        if total_equity > 0 and limits.max_pair_allocation_pct > 0:
            max_alloc = total_equity * limits.max_pair_allocation_pct
            if gross > max_alloc:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_pair_allocation_exceeded ({gross:.1f} > {max_alloc:.1f})",
                    pair_exposure=exposure_info,
                    risk_status="WARNING",
                )

        # 2. Max gross pair exposure
        if limits.max_gross_pair_exposure > 0 and gross > limits.max_gross_pair_exposure:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"max_gross_pair_exposure_exceeded ({gross:.1f} > {limits.max_gross_pair_exposure:.1f})",
                pair_exposure=exposure_info,
                risk_status="WARNING",
            )

        # 3. Max net exposure
        if gross > 0 and limits.max_net_exposure_pct > 0:
            net_fraction = abs(net) / gross
            if net_fraction > limits.max_net_exposure_pct:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_net_exposure_exceeded ({net_fraction * 100:.1f}% > {limits.max_net_exposure_pct * 100:.1f}%)",
                    pair_exposure=exposure_info,
                    risk_status="WARNING",
                )

        # 4. Max leverage
        if limits.max_leverage > 0 and lev > limits.max_leverage:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"max_leverage_exceeded ({lev:.2f}x > {limits.max_leverage:.2f}x)",
                pair_exposure=exposure_info,
                risk_status="WARNING",
            )

        # 5. Max hedge deviation
        if limits.max_hedge_deviation_pct > 0 and dev > limits.max_hedge_deviation_pct:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"max_hedge_deviation_exceeded ({dev * 100:.1f}% > {limits.max_hedge_deviation_pct * 100:.1f}%)",
                pair_exposure=exposure_info,
                risk_status="WARNING",
            )

        # 6. Max holding duration
        if limits.max_holding_duration_bars > 0 and holding > limits.max_holding_duration_bars:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"max_holding_duration_exceeded ({holding} > {limits.max_holding_duration_bars} bars)",
                pair_exposure=exposure_info,
                risk_status="WARNING",
            )

        # 7. Max pair loss
        if limits.max_pair_loss_pct > 0 and loss_pct >= limits.max_pair_loss_pct:
            self.trigger_pair_emergency_exit(
                pair_state.pair_id,
                operator="circuit_breaker",
                reason=f"max_pair_loss_exceeded ({loss_pct:.2f}% >= {limits.max_pair_loss_pct:.2f}%)",
            )
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"max_pair_loss_exceeded ({loss_pct:.2f}% >= {limits.max_pair_loss_pct:.2f}%)",
                pair_exposure=exposure_info,
                risk_status="HALTED",
            )

        # 8. Max spread divergence
        if limits.max_spread_divergence_z > 0 and abs(z_score) >= limits.max_spread_divergence_z:
            self.trigger_pair_emergency_exit(
                pair_state.pair_id,
                operator="circuit_breaker",
                reason=f"max_spread_divergence_exceeded (|{z_score:.2f}| >= {limits.max_spread_divergence_z:.2f})",
            )
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"max_spread_divergence_exceeded (|{z_score:.2f}| >= {limits.max_spread_divergence_z:.2f})",
                pair_exposure=exposure_info,
                risk_status="HALTED",
            )

        max_allowed = total_equity * limits.max_pair_allocation_pct if total_equity > 0 else 0.0
        return StatArbRiskVerdict(
            allowed=True,
            approved=True,
            max_allowed_position=max_allowed,
            pair_exposure=exposure_info,
            risk_status="NORMAL",
        )

    def evaluate_pair_order(
        self,
        pair_id: str,
        action: str,
        pair_state: PairRiskState,
        total_equity: float,
        *,
        is_risk_reducing: bool = False,
    ) -> StatArbRiskVerdict:
        """
        Evaluate pair order against kill-switch, drawdown, loss halts, and pair limits.
        Risk-reducing orders are permitted even during an active halt or emergency exit.
        """
        if is_risk_reducing or action in ("close_spread", "flatten", "exit"):
            return StatArbRiskVerdict(
                allowed=True,
                approved=True,
                reason="risk_reducing_order_permitted",
                risk_status="REDUCING_ONLY",
            )

        if self.limits.kill_switch:
            return StatArbRiskVerdict(allowed=False, approved=False, reason="kill_switch", risk_status="HALTED")
        if self.halted:
            return StatArbRiskVerdict(
                allowed=False, approved=False, reason=self.halt_reason or "risk_halt", risk_status="HALTED"
            )
        if pair_id in self.pair_emergency_exits:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"pair_emergency_exit_active ({pair_id})",
                risk_status="HALTED",
            )

        return self.evaluate_pair_limits(pair_state, total_equity)

    def trigger_pair_emergency_exit(
        self,
        pair_id: str,
        *,
        operator: str = "system",
        reason: str = "pair_emergency_exit",
    ) -> None:
        self.pair_emergency_exits.add(pair_id)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "pair_emergency_halt",
            "pair_id": pair_id,
            "operator": operator,
            "reason": reason,
        }
        self.audit_log.append(entry)
        logger.warning("Pair emergency halt triggered on %s by %s: %s", pair_id, operator, reason)

    def clear_pair_emergency_exit(
        self,
        pair_id: str,
        *,
        operator: str,
        reason: str,
    ) -> None:
        if pair_id not in self.pair_emergency_exits:
            return
        self.pair_emergency_exits.discard(pair_id)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "pair_unhalt",
            "pair_id": pair_id,
            "operator": operator,
            "reason": reason,
        }
        self.audit_log.append(entry)
        logger.info("Pair emergency halt cleared on %s by %s: %s", pair_id, operator, reason)

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
            "pair_emergency_exits": sorted(self.pair_emergency_exits),
            "pair_states": {pid: s.snapshot() for pid, s in self.pair_states.items()},
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
        self.pair_emergency_exits = set(data.get("pair_emergency_exits", []))
        self.pair_states = {
            pid: PairRiskState.from_snapshot(s)
            for pid, s in (data.get("pair_states") or {}).items()
        }

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
