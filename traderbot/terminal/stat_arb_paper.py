from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Literal

from traderbot.algorithms.pair_trading.sizing import calculate_pair_position_sizes
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm, PairSignal
from traderbot.risk.cointegration_monitor import CointegrationHealthMonitor
from traderbot.risk.execution import PairExecutionRiskManager, PairOrderExecutionState
from traderbot.risk.funding import calculate_funding_payment
from traderbot.risk.pair_models import PairRiskState
from traderbot.risk.portfolio import PortfolioRiskManager
from traderbot.analysis.pairs.persistence import (
    close_pair_paper_position,
    record_pair_execution_event,
    record_pair_paper_position,
    record_pair_risk_decision,
    record_pair_strategy_signal,
    update_pair_paper_position,
)

logger = logging.getLogger(__name__)


class StatArbPaperTrader:
    """
    Simulated two-leg statistical arbitrage paper execution engine.
    Honors microstructural frictions (maker/taker fees, spread crossing, slippage),
    discrete perpetual funding settlement, partial fill / legging unwinds, and
    centralized portfolio risk & health circuit breakers.
    """

    def __init__(
        self,
        *,
        pair_id: str,
        symbol_a: str,
        symbol_b: str,
        algorithm: PairTradingAlgorithm,
        risk_manager: PortfolioRiskManager | None = None,
        execution_manager: PairExecutionRiskManager | None = None,
        health_monitor: CointegrationHealthMonitor | None = None,
        initial_cash: float = 10_000.0,
        fee_rate: float = 0.00045,
        slippage_rate: float = 0.0005,
        position_fraction: float = 0.5,
        leverage: float = 1.0,
        exchange: str = "hyperliquid",
        persist: bool = True,
        simulate_leg_b_failure: bool = False,
    ) -> None:
        self.pair_id = pair_id
        self.symbol_a = symbol_a
        self.symbol_b = symbol_b
        self.algorithm = algorithm
        self.risk_manager = risk_manager or PortfolioRiskManager()
        self.execution_manager = execution_manager or PairExecutionRiskManager()
        self.health_monitor = health_monitor or CointegrationHealthMonitor()
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.position_fraction = position_fraction
        self.leverage = leverage
        self.exchange = exchange
        self.persist = persist
        self.simulate_leg_b_failure = simulate_leg_b_failure

        self.position_state: PairRiskState | None = None
        self.current_db_position_id: str | None = None
        self.total_fees = 0.0
        self.total_slippage = 0.0
        self.total_funding_paid = 0.0
        self.total_funding_received = 0.0
        self.realized_pnl = 0.0
        self.unwound_legs_count = 0
        self.trade_count = 0

    @property
    def has_open_position(self) -> bool:
        return self.position_state is not None and self.position_state.status == "OPEN"

    def _calc_fill_price(self, price: float, action: Literal["buy", "sell"]) -> float:
        if action == "buy":
            return price * (1.0 + self.slippage_rate)
        return price * (1.0 - self.slippage_rate)

    def process_bar(
        self,
        bar_a: dict[str, Any],
        bar_b: dict[str, Any],
        *,
        funding_rates: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """
        Process incoming synchronous bars for Asset A and Asset B:
        1. Mark-to-market prices and discrete funding.
        2. Evaluate health monitor & circuit breakers.
        3. Pass bars to algorithm -> get signal.
        4. Execute entry/exit/emergency actions.
        """
        price_a = float(bar_a["close"])
        price_b = float(bar_b["close"])
        timestamp = int(bar_a["timestamp"])

        # 1. Update active position mark-to-market
        if self.has_open_position and self.position_state is not None:
            self.position_state.update_prices(price_a, price_b)
            self.position_state.holding_bars += 1

            # Process funding settlement if rates supplied (hourly settlement)
            if funding_rates is not None:
                rate_a, rate_b = funding_rates
                side_a = "LONG" if self.position_state.leg_a_qty > 0 else "SHORT"
                side_b = "LONG" if self.position_state.leg_b_qty > 0 else "SHORT"

                pay_a = calculate_funding_payment(abs(self.position_state.leg_a_qty), price_a, side_a, rate_a)
                pay_b = calculate_funding_payment(abs(self.position_state.leg_b_qty), price_b, side_b, rate_b)
                net_pay = pay_a + pay_b

                if net_pay > 0:
                    self.total_funding_paid += net_pay
                    self.cash -= net_pay
                else:
                    self.total_funding_received += abs(net_pay)
                    self.cash += abs(net_pay)

            # Check health monitor for structural breaks or unit root loss
            if self.position_state.holding_bars >= 10:
                health = self.health_monitor.assess(
                    current_spread=self.position_state.current_spread,
                    entry_spread=self.position_state.entry_spread,
                    entry_spread_std=self.position_state.entry_spread_std,
                )
                if health.is_broken:
                    logger.warning("Cointegration broken for %s: %s", self.pair_id, health.reasons)
                    return self.emergency_flatten(reason="cointegration_breakdown")

            # Check portfolio risk halt
            if self.risk_manager.halted:
                return self.emergency_flatten(reason="portfolio_risk_halt")

            # Update DB mark-to-market
            if self.persist and self.current_db_position_id:
                update_pair_paper_position(
                    position_id=self.current_db_position_id,
                    unrealized_pnl=self.position_state.unrealized_pnl,
                    total_fees=self.total_fees,
                    total_funding=(self.total_funding_paid - self.total_funding_received),
                    snapshot=self.position_state.snapshot(),
                )

        # 2. Evaluate strategy signal via pair_signal on aligned bar
        aligned_bar = {
            "timestamp": timestamp,
            "open": float(bar_a.get("open", price_a)),
            "close": price_a,
            "hedge_open": float(bar_b.get("open", price_b)),
            "hedge_close": price_b,
        }
        signal_action = self.algorithm.pair_signal(aligned_bar)
        snap = self.algorithm.last_snapshot
        current_spread = snap.spread_pct if snap else 0.0
        current_z = snap.z_score if snap else 0.0

        # Persist evaluated signal
        if self.persist:
            record_pair_strategy_signal(
                pair_id=self.pair_id,
                action=signal_action,
                spread=current_spread,
                z_score=current_z,
                dominant_price=price_a,
                hedge_price=price_b,
                hedge_ratio=self.algorithm.hedge_ratio,
                dominant_qty=0.0,
                hedge_qty=0.0,
                metadata={"spread_model": self.algorithm.spread_model},
            )

        # 3. Action dispatch
        if signal_action in ("long_spread", "short_spread") and not self.has_open_position:
            self._handle_entry(signal_action, current_spread, current_z, price_a, price_b, timestamp)
        elif signal_action == "close_spread" and self.has_open_position:
            self._handle_exit(current_spread, current_z, price_a, price_b, timestamp, reason="strategy_exit")

        return self.snapshot()

    def _handle_entry(
        self,
        direction: str,
        spread: float,
        z_score: float,
        price_a: float,
        price_b: float,
        timestamp: int,
    ) -> None:
        hedge_ratio = self.algorithm.hedge_ratio or 1.0

        # Sizing
        sizing = calculate_pair_position_sizes(
            capital=self.cash,
            close_a=price_a,
            close_b=price_b,
            hedge_ratio=hedge_ratio,
            direction="long_spread" if direction == "long_spread" else "short_spread",
            position_fraction=self.position_fraction,
            leverage=self.leverage,
        )
        qty_a = sizing.leg_a_qty
        qty_b = sizing.leg_b_qty
        notional_a = abs(qty_a) * price_a
        notional_b = abs(qty_b) * price_b

        # Risk approval check
        verdict = self.risk_manager.evaluate_pair_entry(
            pair_id=self.pair_id,
            symbol_a=self.symbol_a,
            symbol_b=self.symbol_b,
            notional_a=notional_a,
            notional_b=notional_b,
            total_equity=self.cash,
        )
        if not verdict.allowed:
            if self.persist:
                record_pair_risk_decision(
                    pair_id=self.pair_id,
                    check_type="ENTRY",
                    verdict="REJECTED",
                    reason=verdict.reason,
                )
            return

        # Simulate execution of Leg A
        act_a: Literal["buy", "sell"] = "buy" if qty_a > 0 else "sell"
        fill_price_a = self._calc_fill_price(price_a, act_a)
        fee_a = abs(qty_a) * fill_price_a * self.fee_rate
        slip_a = abs(fill_price_a - price_a) * abs(qty_a)
        self.total_fees += fee_a
        self.total_slippage += slip_a
        self.cash -= fee_a

        # Check for simulated Leg B failure
        if self.simulate_leg_b_failure:
            # Policy immediate_flatten: immediately unwind Leg A
            unwind_act: Literal["buy", "sell"] = "sell" if qty_a > 0 else "buy"
            fill_unwind_a = self._calc_fill_price(price_a, unwind_act)
            fee_unwind = abs(qty_a) * fill_unwind_a * self.fee_rate
            slip_unwind = abs(fill_unwind_a - price_a) * abs(qty_a)
            self.total_fees += fee_unwind
            self.total_slippage += slip_unwind
            self.cash -= fee_unwind
            pnl_unwind = qty_a * (fill_unwind_a - fill_price_a)
            self.cash += pnl_unwind
            self.realized_pnl += pnl_unwind
            self.unwound_legs_count += 1
            if self.persist:
                record_pair_execution_event(
                    position_id=None,
                    pair_id=self.pair_id,
                    leg="dominant",
                    action=act_a,
                    requested_qty=abs(qty_a),
                    filled_qty=abs(qty_a),
                    fill_price=fill_price_a,
                    fee=fee_a,
                    slippage=slip_a,
                    execution_status="UNWOUND",
                    notes="leg_b_failed_immediate_flatten",
                )
            return

        # Normal execution: Leg B fills
        act_b: Literal["buy", "sell"] = "buy" if qty_b > 0 else "sell"
        fill_price_b = self._calc_fill_price(price_b, act_b)
        fee_b = abs(qty_b) * fill_price_b * self.fee_rate
        slip_b = abs(fill_price_b - price_b) * abs(qty_b)
        self.total_fees += fee_b
        self.total_slippage += slip_b
        self.cash -= fee_b

        self.position_state = PairRiskState(
            pair_id=self.pair_id,
            symbol_a=self.symbol_a,
            symbol_b=self.symbol_b,
            leg_a_qty=qty_a,
            leg_b_qty=qty_b,
            entry_price_a=fill_price_a,
            entry_price_b=fill_price_b,
            current_price_a=price_a,
            current_price_b=price_b,
            hedge_ratio=hedge_ratio,
            allocated_capital=self.cash * self.position_fraction,
            entry_spread=spread,
            current_spread=spread,
            current_z_score=z_score,
            status="OPEN",
        )
        self.risk_manager.register_pair(self.position_state)
        self.trade_count += 2

        if self.persist:
            self.current_db_position_id = record_pair_paper_position(
                pair_id=self.pair_id,
                entry_spread=spread,
                entry_z_score=z_score,
                leg_a_qty=qty_a,
                leg_b_qty=qty_b,
                entry_price_a=fill_price_a,
                entry_price_b=fill_price_b,
                snapshot=self.position_state.snapshot(),
            )
            record_pair_execution_event(
                position_id=self.current_db_position_id,
                pair_id=self.pair_id,
                leg="dominant",
                action=act_a,
                requested_qty=abs(qty_a),
                filled_qty=abs(qty_a),
                fill_price=fill_price_a,
                fee=fee_a,
                slippage=slip_a,
                execution_status="FILLED",
            )
            record_pair_execution_event(
                position_id=self.current_db_position_id,
                pair_id=self.pair_id,
                leg="hedge",
                action=act_b,
                requested_qty=abs(qty_b),
                filled_qty=abs(qty_b),
                fill_price=fill_price_b,
                fee=fee_b,
                slippage=slip_b,
                execution_status="FILLED",
            )

    def _handle_exit(
        self,
        spread: float,
        z_score: float,
        price_a: float,
        price_b: float,
        timestamp: int,
        reason: str = "exit",
        status: str = "CLOSED",
    ) -> None:
        if not self.position_state:
            return

        pos = self.position_state
        act_a: Literal["buy", "sell"] = "sell" if pos.leg_a_qty > 0 else "buy"
        act_b: Literal["buy", "sell"] = "sell" if pos.leg_b_qty > 0 else "buy"

        exit_price_a = self._calc_fill_price(price_a, act_a)
        exit_price_b = self._calc_fill_price(price_b, act_b)

        fee_a = abs(pos.leg_a_qty) * exit_price_a * self.fee_rate
        fee_b = abs(pos.leg_b_qty) * exit_price_b * self.fee_rate
        self.total_fees += fee_a + fee_b
        self.cash -= (fee_a + fee_b)

        pnl_a = pos.leg_a_qty * (exit_price_a - pos.entry_price_a)
        pnl_b = pos.leg_b_qty * (exit_price_b - pos.entry_price_b)
        trip_pnl = pnl_a + pnl_b
        self.realized_pnl += trip_pnl
        self.cash += trip_pnl
        self.trade_count += 2

        pos.status = status
        exit_spread = spread
        exit_z = z_score

        if self.persist and self.current_db_position_id:
            close_pair_paper_position(
                position_id=self.current_db_position_id,
                exit_spread=exit_spread,
                exit_z_score=exit_z,
                exit_price_a=exit_price_a,
                exit_price_b=exit_price_b,
                realized_pnl=trip_pnl,
                total_fees=self.total_fees,
                total_funding=(self.total_funding_paid - self.total_funding_received),
                status=status,
                snapshot=pos.snapshot(),
            )
            record_pair_execution_event(
                position_id=self.current_db_position_id,
                pair_id=self.pair_id,
                leg="dominant",
                action=act_a,
                requested_qty=abs(pos.leg_a_qty),
                filled_qty=abs(pos.leg_a_qty),
                fill_price=exit_price_a,
                fee=fee_a,
                execution_status="FILLED",
                notes=reason,
            )
            record_pair_execution_event(
                position_id=self.current_db_position_id,
                pair_id=self.pair_id,
                leg="hedge",
                action=act_b,
                requested_qty=abs(pos.leg_b_qty),
                filled_qty=abs(pos.leg_b_qty),
                fill_price=exit_price_b,
                fee=fee_b,
                execution_status="FILLED",
                notes=reason,
            )

        self.risk_manager.close_pair(self.pair_id)
        self.position_state = None
        self.current_db_position_id = None

    def emergency_flatten(self, reason: str = "emergency_flatten", operator: str = "system") -> dict[str, Any]:
        """Audited emergency flatten for open positions."""
        if not self.position_state:
            return {"status": "NO_OPEN_POSITION", "reason": reason}

        pos = self.position_state
        price_a = pos.current_price_a
        price_b = pos.current_price_b
        now_ts = int(time.time())

        if self.persist:
            record_pair_risk_decision(
                pair_id=self.pair_id,
                check_type="EMERGENCY",
                verdict="EMERGENCY_EXIT",
                reason=f"{reason} by {operator}",
            )

        self._handle_exit(
            pos.current_spread,
            pos.current_z_score,
            price_a,
            price_b,
            now_ts,
            reason=reason,
            status="EMERGENCY_EXIT",
        )
        return {"status": "EMERGENCY_EXIT", "pair_id": self.pair_id, "reason": reason, "operator": operator}

    def snapshot(self) -> dict[str, Any]:
        """Complete mark-to-market snapshot of the paper trader."""
        unrealized = self.position_state.unrealized_pnl if self.position_state else 0.0
        marked_equity = self.cash + unrealized
        net_funding = self.total_funding_paid - self.total_funding_received

        return {
            "pair_id": self.pair_id,
            "exchange": self.exchange,
            "has_open_position": self.has_open_position,
            "cash": round(self.cash, 4),
            "marked_equity": round(marked_equity, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(unrealized, 4),
            "total_fees": round(self.total_fees, 4),
            "total_slippage": round(self.total_slippage, 4),
            "net_funding": round(net_funding, 4),
            "trade_count": self.trade_count,
            "unwound_legs_count": self.unwound_legs_count,
            "position": self.position_state.snapshot() if self.position_state else None,
        }
