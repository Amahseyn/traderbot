from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

from traderbot.risk.manager import RiskVerdict
from traderbot.risk.pair_models import (
    PairExposureInfo,
    PairRiskState,
    PortfolioExposureInfo,
    StatArbRiskVerdict,
)

logger = logging.getLogger(__name__)


@dataclass
class PortfolioRiskLimits:
    max_aggregate_capital_cap: float = 10_000_000.0
    portfolio_daily_loss_limit_pct: float = 5.0
    portfolio_max_drawdown_pct: float = 15.0
    max_concurrent_positions: int = 5
    max_gross_exposure_equity: float = 1.0
    kill_switch: bool = False
    # Statistical Arbitrage Multi-Pair & Concentration Controls
    max_concurrent_pairs: int = 3
    max_portfolio_gross_notional: float = 50_000_000.0
    max_portfolio_net_notional_pct: float = 0.50
    max_symbol_concentration_pct: float = 0.30  # Max gross on any single symbol / equity
    max_shared_symbol_pairs: int = 2  # Max pairs allowed to share an underlying asset
    min_available_margin_pct: float = 0.20  # Minimum 20% available margin buffer
    max_spread_correlation: float = 0.70  # Max correlation allowed between pair spreads
    maintenance_margin_pct: float = 0.05  # Base 5% maintenance margin requirement (20x leverage)


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
    active_pairs: dict[str, PairRiskState] = field(default_factory=dict)
    pair_spread_histories: dict[str, list[float]] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_date:
            self.session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def trigger_kill_switch(
        self,
        *,
        operator: str = "system",
        reason: str = "manual_portfolio_kill_switch",
    ) -> None:
        """Trigger an emergency portfolio halt with audited operator attribution."""
        self.halted = True
        self.halt_reason = reason
        self.limits.kill_switch = True
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "portfolio_kill_switch",
            "operator": operator,
            "reason": reason,
        }
        self.audit_log.append(entry)
        logger.warning("Emergency portfolio kill switch triggered by operator '%s': %s", operator, reason)

    def unhalt(self, *, operator: str, reason: str) -> None:
        """Clear latching portfolio risk halt with audited operator attribution."""
        if not self.halted and not self.limits.kill_switch:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "portfolio_unhalt",
            "operator": operator,
            "reason": reason,
            "previous_halt_reason": self.halt_reason,
        }
        self.audit_log.append(entry)
        self.halted = False
        self.halt_reason = ""
        self.limits.kill_switch = False
        logger.info("Portfolio risk halt cleared by operator '%s': %s", operator, reason)

    def reset_session(self, total_equity: float, *, operator: str = "system", reason: str = "session_reset") -> None:
        self.session_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.day_start_equity = total_equity
        self.peak_equity = total_equity
        self.last_equity = total_equity
        if self.halted or self.limits.kill_switch:
            self.unhalt(operator=operator, reason=reason)
        else:
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

    def register_pair(
        self,
        pair_state: PairRiskState,
        spread_history: list[float] | None = None,
    ) -> None:
        self.active_pairs[pair_state.pair_id] = pair_state
        if spread_history is not None:
            self.pair_spread_histories[pair_state.pair_id] = list(spread_history)

    def close_pair(self, pair_id: str) -> None:
        self.active_pairs.pop(pair_id, None)
        self.pair_spread_histories.pop(pair_id, None)

    def update_pair_legs(
        self,
        pair_id: str,
        *,
        leg_a_qty: float,
        leg_b_qty: float,
        price_a: float,
        price_b: float,
    ) -> None:
        pair = self.active_pairs.get(pair_id)
        if pair is not None:
            pair.leg_a_qty = leg_a_qty
            pair.leg_b_qty = leg_b_qty
            pair.update_prices(price_a, price_b)

    def get_shared_symbols(self) -> dict[str, list[str]]:
        """Index mapping each underlying asset to active pairs trading it."""
        mapping: dict[str, list[str]] = {}
        for pid, pair in self.active_pairs.items():
            for sym in (pair.symbol_a, pair.symbol_b):
                if sym:
                    mapping.setdefault(sym, []).append(pid)
        return mapping

    def get_symbol_gross_exposure(self, symbol: str) -> float:
        """Total gross dollar exposure on a symbol across all open pairs."""
        gross = 0.0
        for pair in self.active_pairs.values():
            if pair.symbol_a == symbol:
                gross += abs(pair.leg_a_notional)
            if pair.symbol_b == symbol:
                gross += abs(pair.leg_b_notional)
        return gross

    def get_symbol_net_exposure(self, symbol: str) -> float:
        """Signed net dollar exposure on a symbol across all open pairs."""
        net = 0.0
        for pair in self.active_pairs.values():
            if pair.symbol_a == symbol:
                net += pair.leg_a_notional
            if pair.symbol_b == symbol:
                net += pair.leg_b_notional
        return net

    def get_aggregate_long_exposure(self) -> float:
        """Sum of positive net exposures across all symbols."""
        symbol_nets: dict[str, float] = {}
        for pair in self.active_pairs.values():
            symbol_nets[pair.symbol_a] = symbol_nets.get(pair.symbol_a, 0.0) + pair.leg_a_notional
            symbol_nets[pair.symbol_b] = symbol_nets.get(pair.symbol_b, 0.0) + pair.leg_b_notional
        return sum(val for val in symbol_nets.values() if val > 0)

    def get_aggregate_short_exposure(self) -> float:
        """Sum of negative net exposures (as positive magnitude) across all symbols."""
        symbol_nets: dict[str, float] = {}
        for pair in self.active_pairs.values():
            symbol_nets[pair.symbol_a] = symbol_nets.get(pair.symbol_a, 0.0) + pair.leg_a_notional
            symbol_nets[pair.symbol_b] = symbol_nets.get(pair.symbol_b, 0.0) + pair.leg_b_notional
        return sum(abs(val) for val in symbol_nets.values() if val < 0)

    def get_portfolio_gross_notional(self) -> float:
        """Total gross notional across all legs of all active pairs."""
        return sum(pair.gross_notional for pair in self.active_pairs.values())

    def get_portfolio_net_notional(self) -> float:
        """Total signed net notional across all active pairs."""
        return sum(pair.net_notional for pair in self.active_pairs.values())

    def get_margin_metrics(self, total_equity: float) -> tuple[float, float, float]:
        """
        Compute (margin_used, available_margin, margin_ratio).
        Two legs are NOT independent risk-free positions; gross notional consumes margin.
        """
        gross = self.get_portfolio_gross_notional()
        margin_used = gross * self.limits.maintenance_margin_pct
        available = max(0.0, total_equity - margin_used)
        ratio = (margin_used / total_equity) if total_equity > 0 else 1.0
        return margin_used, available, ratio

    def get_portfolio_exposure_info(self, total_equity: float) -> PortfolioExposureInfo:
        margin_used, available_margin, margin_ratio = self.get_margin_metrics(total_equity)
        return PortfolioExposureInfo(
            total_equity=total_equity,
            aggregate_long_notional=self.get_aggregate_long_exposure(),
            aggregate_short_notional=self.get_aggregate_short_exposure(),
            gross_notional=self.get_portfolio_gross_notional(),
            net_notional=self.get_portfolio_net_notional(),
            margin_used=margin_used,
            available_margin=available_margin,
            margin_ratio=margin_ratio,
            active_pair_count=len(self.active_pairs),
            open_pairs=sorted(self.active_pairs.keys()),
            shared_symbols=self.get_shared_symbols(),
        )

    def evaluate_entry(
        self,
        symbol: str,
        *,
        requested_notional: float,
        total_equity: float,
        current_gross_notional: float = 0.0,
    ) -> RiskVerdict:
        """Single-asset position evaluation (preserved for backward compatibility)."""
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

    def evaluate_pair_entry(
        self,
        *,
        pair_id: str,
        symbol_a: str,
        symbol_b: str,
        notional_a: float,
        notional_b: float,
        total_equity: float,
        spread_history: list[float] | None = None,
    ) -> StatArbRiskVerdict:
        """
        Evaluate proposed pair entry against multi-pair portfolio risk:
        - Portfolio daily loss & drawdown halts
        - Max concurrent pairs
        - Shared symbols between pairs
        - Single-symbol concentration
        - Aggregate gross/net notional
        - Available margin depletion
        - Correlated spread exposure (via Correlation Scanner)
        """
        self._roll_session_if_new_day(total_equity)
        exp_info = self.get_portfolio_exposure_info(total_equity)

        if self.limits.kill_switch:
            return StatArbRiskVerdict(
                allowed=False, approved=False, reason="portfolio_kill_switch", portfolio_exposure=exp_info, risk_status="HALTED"
            )
        if self.halted:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=self.halt_reason or "portfolio_halt",
                portfolio_exposure=exp_info,
                risk_status="HALTED",
            )

        self.update_mark(total_equity)

        # 1. Daily Loss Limit
        if self.day_start_equity and self.day_start_equity > 0:
            day_loss_pct = (total_equity / self.day_start_equity - 1.0) * 100.0
            if day_loss_pct <= -abs(self.limits.portfolio_daily_loss_limit_pct):
                self.halted = True
                self.halt_reason = "portfolio_daily_loss_limit"
                return StatArbRiskVerdict(
                    allowed=False, approved=False, reason=self.halt_reason, portfolio_exposure=exp_info, risk_status="HALTED"
                )

        # 2. Maximum Drawdown
        if self.peak_equity and self.peak_equity > 0:
            drawdown_pct = (total_equity / self.peak_equity - 1.0) * 100.0
            if drawdown_pct <= -abs(self.limits.portfolio_max_drawdown_pct):
                self.halted = True
                self.halt_reason = "portfolio_max_drawdown"
                return StatArbRiskVerdict(
                    allowed=False, approved=False, reason=self.halt_reason, portfolio_exposure=exp_info, risk_status="HALTED"
                )

        # 3. Max Concurrent Pairs
        if pair_id not in self.active_pairs:
            if len(self.active_pairs) >= self.limits.max_concurrent_pairs:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_concurrent_pairs_reached ({len(self.active_pairs)}/{self.limits.max_concurrent_pairs})",
                    portfolio_exposure=exp_info,
                    risk_status="WARNING",
                )

        # 4. Shared Symbols between pairs
        shared_map = self.get_shared_symbols()
        for sym in (symbol_a, symbol_b):
            existing_pairs = shared_map.get(sym, [])
            if pair_id not in existing_pairs and len(existing_pairs) >= self.limits.max_shared_symbol_pairs:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_shared_symbol_pairs_reached ({sym}: {len(existing_pairs)}/{self.limits.max_shared_symbol_pairs})",
                    portfolio_exposure=exp_info,
                    risk_status="WARNING",
                )

        # 5. Single-Symbol Concentration Limit
        if total_equity > 0 and self.limits.max_symbol_concentration_pct > 0:
            max_sym_notional = total_equity * self.limits.max_symbol_concentration_pct
            projected_a = self.get_symbol_gross_exposure(symbol_a) + abs(notional_a)
            if projected_a > max_sym_notional:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_symbol_concentration_exceeded ({symbol_a}: {projected_a:.1f} > {max_sym_notional:.1f})",
                    portfolio_exposure=exp_info,
                    risk_status="WARNING",
                )
            projected_b = self.get_symbol_gross_exposure(symbol_b) + abs(notional_b)
            if projected_b > max_sym_notional:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_symbol_concentration_exceeded ({symbol_b}: {projected_b:.1f} > {max_sym_notional:.1f})",
                    portfolio_exposure=exp_info,
                    risk_status="WARNING",
                )

        # 6. Gross Exposure & Available Margin
        requested_gross = abs(notional_a) + abs(notional_b)
        projected_gross = self.get_portfolio_gross_notional() + requested_gross

        if total_equity > 0 and self.limits.max_gross_exposure_equity > 0:
            max_gross_equity = total_equity * self.limits.max_gross_exposure_equity
            if projected_gross > max_gross_equity:
                return StatArbRiskVerdict(
                    allowed=False,
                    approved=False,
                    reason=f"max_gross_exposure_exceeded ({projected_gross:.1f} > {max_gross_equity:.1f})",
                    portfolio_exposure=exp_info,
                    risk_status="WARNING",
                )

        projected_margin_used = projected_gross * self.limits.maintenance_margin_pct
        projected_available = total_equity - projected_margin_used
        min_buffer = total_equity * self.limits.min_available_margin_pct

        if projected_available < min_buffer:
            return StatArbRiskVerdict(
                allowed=False,
                approved=False,
                reason=f"insufficient_available_margin ({projected_available:.1f} < {min_buffer:.1f} buffer required)",
                portfolio_exposure=exp_info,
                risk_status="WARNING",
            )

        # 7. Correlation-Aware Exposure: Cross-Pair Spread Correlation
        if spread_history and len(spread_history) >= 10:
            from traderbot.analysis.correlation.metrics import pearson_correlation

            for other_pid, other_spread in self.pair_spread_histories.items():
                if other_pid == pair_id or len(other_spread) < 10:
                    continue
                min_len = min(len(spread_history), len(other_spread))
                s1 = spread_history[-min_len:]
                s2 = other_spread[-min_len:]
                r = pearson_correlation(s1, s2)
                if r > self.limits.max_spread_correlation:
                    return StatArbRiskVerdict(
                        allowed=False,
                        approved=False,
                        reason=f"excessive_spread_correlation ({r:.2f} > {self.limits.max_spread_correlation:.2f} with {other_pid})",
                        portfolio_exposure=exp_info,
                        risk_status="WARNING",
                    )

        return StatArbRiskVerdict(
            allowed=True,
            approved=True,
            portfolio_exposure=exp_info,
            risk_status="NORMAL",
        )

    def evaluate_pair_order(
        self,
        *,
        pair_id: str,
        action: str,
        notional_a: float,
        notional_b: float,
        total_equity: float,
        symbol_a: str = "",
        symbol_b: str = "",
        is_risk_reducing: bool = False,
    ) -> StatArbRiskVerdict:
        """
        Evaluate pair order at portfolio level.
        Risk-reducing orders (closing/flattening open exposure) are permitted even during halts.
        """
        if is_risk_reducing or action in ("close_spread", "flatten", "exit"):
            return StatArbRiskVerdict(
                allowed=True,
                approved=True,
                reason="risk_reducing_order_permitted",
                portfolio_exposure=self.get_portfolio_exposure_info(total_equity),
                risk_status="REDUCING_ONLY",
            )

        return self.evaluate_pair_entry(
            pair_id=pair_id,
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            notional_a=notional_a,
            notional_b=notional_b,
            total_equity=total_equity,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "limits": {
                "max_aggregate_capital_cap": self.limits.max_aggregate_capital_cap,
                "portfolio_daily_loss_limit_pct": self.limits.portfolio_daily_loss_limit_pct,
                "portfolio_max_drawdown_pct": self.limits.portfolio_max_drawdown_pct,
                "max_concurrent_positions": self.limits.max_concurrent_positions,
                "max_gross_exposure_equity": self.limits.max_gross_exposure_equity,
                "kill_switch": self.limits.kill_switch,
                "max_concurrent_pairs": self.limits.max_concurrent_pairs,
                "max_portfolio_gross_notional": self.limits.max_portfolio_gross_notional,
                "max_portfolio_net_notional_pct": self.limits.max_portfolio_net_notional_pct,
                "max_symbol_concentration_pct": self.limits.max_symbol_concentration_pct,
                "max_shared_symbol_pairs": self.limits.max_shared_symbol_pairs,
                "min_available_margin_pct": self.limits.min_available_margin_pct,
                "max_spread_correlation": self.limits.max_spread_correlation,
                "maintenance_margin_pct": self.limits.maintenance_margin_pct,
            },
            "session_date": self.session_date,
            "day_start_equity": self.day_start_equity,
            "peak_equity": self.peak_equity,
            "last_equity": self.last_equity,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "active_positions": sorted(self.active_positions),
            "active_pairs": {pid: p.snapshot() for pid, p in self.active_pairs.items()},
            "pair_spread_histories": {pid: list(hist) for pid, hist in self.pair_spread_histories.items()},
            "audit_log": list(self.audit_log),
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
        self.active_pairs = {
            pid: PairRiskState.from_snapshot(p_data)
            for pid, p_data in (data.get("active_pairs") or {}).items()
        }
        self.pair_spread_histories = {
            pid: list(hist) for pid, hist in (data.get("pair_spread_histories") or {}).items()
        }
        self.audit_log = list(data.get("audit_log", []))

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
