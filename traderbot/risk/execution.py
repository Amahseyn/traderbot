from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

from traderbot.risk.pair_models import ExecutionRiskAssessment

PairLeggingPolicy = Literal["immediate_flatten", "retry_hedge"]


@dataclass(slots=True)
class PairOrderExecutionState:
    """State tracking for two-leg order execution lifecycle."""

    pair_id: str
    symbol_a: str
    symbol_b: str
    target_qty_a: float
    target_qty_b: float
    filled_qty_a: float = 0.0
    filled_qty_b: float = 0.0
    quote_price_a: float = 0.0
    quote_price_b: float = 0.0
    avg_fill_price_a: float = 0.0
    avg_fill_price_b: float = 0.0
    status_a: str = "PENDING"  # 'PENDING', 'FILLED', 'PARTIALLY_FILLED', 'TIMEOUT', 'FAILED', 'UNKNOWN'
    status_b: str = "PENDING"
    stop_placed: bool = False
    stop_placement_failed: bool = False
    target_hedge_ratio: float = 1.0
    max_hedge_deviation_pct: float = 0.10
    max_slippage_pct: float = 0.005
    order_book_depth_a: float = 0.0
    order_book_depth_b: float = 0.0


class PairExecutionRiskManager:
    """
    Manages two-leg statistical arbitrage execution risk and reconciliation.

    Core invariant:
      A two-leg trade must NEVER be considered fully established until both legs
      are reconciled within strict hedge ratio tolerances and protective stops are verified.
    """

    def __init__(
        self,
        *,
        min_depth_multiple: float = 2.0,
        max_slippage_pct: float = 0.005,
        max_hedge_deviation_pct: float = 0.10,
        legging_policy: PairLeggingPolicy = "immediate_flatten",
    ) -> None:
        self.min_depth_multiple = min_depth_multiple
        self.max_slippage_pct = max_slippage_pct
        self.max_hedge_deviation_pct = max_hedge_deviation_pct
        self.legging_policy = legging_policy

    def verify_pre_trade_liquidity(
        self,
        *,
        target_qty_a: float,
        target_qty_b: float,
        quote_price_a: float,
        quote_price_b: float,
        depth_a: float,
        depth_b: float,
    ) -> tuple[bool, str]:
        """
        Verify top-of-book depth on both legs exceeds the minimum depth multiple
        relative to the requested order notional.
        """
        notional_a = abs(target_qty_a) * quote_price_a
        notional_b = abs(target_qty_b) * quote_price_b

        req_depth_a = notional_a * self.min_depth_multiple
        req_depth_b = notional_b * self.min_depth_multiple

        if depth_a < req_depth_a:
            return (
                False,
                f"insufficient_order_book_depth on leg A ({depth_a:.1f} < {req_depth_a:.1f} USD required)",
            )
        if depth_b < req_depth_b:
            return (
                False,
                f"insufficient_order_book_depth on leg B ({depth_b:.1f} < {req_depth_b:.1f} USD required)",
            )

        return True, ""

    def evaluate_execution_progress(
        self,
        state: PairOrderExecutionState,
    ) -> ExecutionRiskAssessment:
        notes: list[str] = []
        fill_pct_a = abs(state.filled_qty_a) / abs(state.target_qty_a) if abs(state.target_qty_a) > 0 else 0.0
        fill_pct_b = abs(state.filled_qty_b) / abs(state.target_qty_b) if abs(state.target_qty_b) > 0 else 0.0

        # 1. Slippage calculation
        slippage_a = (
            abs(state.avg_fill_price_a - state.quote_price_a) / state.quote_price_a
            if state.quote_price_a > 0 and state.avg_fill_price_a > 0
            else 0.0
        )
        slippage_b = (
            abs(state.avg_fill_price_b - state.quote_price_b) / state.quote_price_b
            if state.quote_price_b > 0 and state.avg_fill_price_b > 0
            else 0.0
        )

        effective_max_slippage = state.max_slippage_pct or self.max_slippage_pct
        if slippage_a > effective_max_slippage:
            notes.append(f"Excessive slippage on Leg A ({slippage_a * 100:.2f}% > {effective_max_slippage * 100:.2f}%)")
        if slippage_b > effective_max_slippage:
            notes.append(f"Excessive slippage on Leg B ({slippage_b * 100:.2f}% > {effective_max_slippage * 100:.2f}%)")

        # 2. Stop placement failure check (Phase 0 safety: fail-closed emergency flatten)
        if state.stop_placement_failed:
            notes.append("Protective stop placement failed; emergency flatten required")
            return ExecutionRiskAssessment(
                status="STOP_PLACEMENT_FAILED_FLATTEN",
                reconciled=False,
                leg_a_fill_pct=fill_pct_a,
                leg_b_fill_pct=fill_pct_b,
                slippage_a_pct=slippage_a,
                slippage_b_pct=slippage_b,
                depth_sufficient=True,
                legging_risk_warning=True,
                notes=notes,
            )

        # 3. Timeout / Unknown order status handling
        status_a = state.status_a.upper()
        status_b = state.status_b.upper()
        has_unknown = status_a in ("TIMEOUT", "UNKNOWN") or status_b in ("TIMEOUT", "UNKNOWN")
        if has_unknown:
            notes.append(
                "Order timeout or unknown order status detected. State is UNKNOWN, never assumed failed. "
                "Querying exchange order book state before retrying."
            )
            return ExecutionRiskAssessment(
                status="UNKNOWN_ORDER_STATUS",
                reconciled=False,
                leg_a_fill_pct=fill_pct_a,
                leg_b_fill_pct=fill_pct_b,
                slippage_a_pct=slippage_a,
                slippage_b_pct=slippage_b,
                depth_sufficient=True,
                legging_risk_warning=True,
                notes=notes,
            )

        # 4. One-leg execution failure / Legging Risk
        leg_a_has_exposure = fill_pct_a > 0
        leg_b_has_exposure = fill_pct_b > 0

        if (leg_a_has_exposure and status_b == "FAILED") or (leg_b_has_exposure and status_a == "FAILED"):
            failed_leg = "B" if status_b == "FAILED" else "A"
            if self.legging_policy == "immediate_flatten":
                notes.append(
                    f"One-leg execution failure on Leg {failed_leg}; immediate emergency flatten triggered"
                )
                status = "LEGGING_FAILURE_FLATTEN"
            else:
                notes.append(f"One-leg execution failure on Leg {failed_leg}; retry hedge dispatched")
                status = "LEGGING_FAILURE_RETRY"

            return ExecutionRiskAssessment(
                status=status,
                reconciled=False,
                leg_a_fill_pct=fill_pct_a,
                leg_b_fill_pct=fill_pct_b,
                slippage_a_pct=slippage_a,
                slippage_b_pct=slippage_b,
                depth_sufficient=True,
                legging_risk_warning=True,
                notes=notes,
            )

        # 5. Partial fill hedge ratio imbalance
        if leg_a_has_exposure and leg_b_has_exposure:
            filled_notional_a = abs(state.filled_qty_a) * (state.avg_fill_price_a or state.quote_price_a)
            filled_notional_b = abs(state.filled_qty_b) * (state.avg_fill_price_b or state.quote_price_b)

            if filled_notional_a > 0:
                actual_ratio = filled_notional_b / filled_notional_a
                target_ratio = state.target_hedge_ratio
                ratio_deviation = abs(actual_ratio - target_ratio) / target_ratio if target_ratio > 0 else 0.0

                effective_max_deviation = state.max_hedge_deviation_pct or self.max_hedge_deviation_pct
                if ratio_deviation > effective_max_deviation and (fill_pct_a < 0.99 or fill_pct_b < 0.99):
                    notes.append(
                        f"Partial fill hedge imbalance ({ratio_deviation * 100:.1f}% deviation > {effective_max_deviation * 100:.1f}%)"
                    )
                    return ExecutionRiskAssessment(
                        status="PARTIAL_FILL_HEDGE_IMBALANCE",
                        reconciled=False,
                        leg_a_fill_pct=fill_pct_a,
                        leg_b_fill_pct=fill_pct_b,
                        slippage_a_pct=slippage_a,
                        slippage_b_pct=slippage_b,
                        depth_sufficient=True,
                        legging_risk_warning=True,
                        notes=notes,
                    )

        # 6. Full reconciliation check
        both_filled = fill_pct_a >= 0.99 and fill_pct_b >= 0.99
        if both_filled and (state.stop_placed or not state.stop_placement_failed):
            return ExecutionRiskAssessment(
                status="RECONCILED",
                reconciled=True,
                leg_a_fill_pct=fill_pct_a,
                leg_b_fill_pct=fill_pct_b,
                slippage_a_pct=slippage_a,
                slippage_b_pct=slippage_b,
                depth_sufficient=True,
                legging_risk_warning=False,
                notes=notes,
            )

        return ExecutionRiskAssessment(
            status="IN_PROGRESS",
            reconciled=False,
            leg_a_fill_pct=fill_pct_a,
            leg_b_fill_pct=fill_pct_b,
            slippage_a_pct=slippage_a,
            slippage_b_pct=slippage_b,
            depth_sufficient=True,
            legging_risk_warning=bool(fill_pct_a != fill_pct_b),
            notes=notes,
        )

