from __future__ import annotations

from typing import Literal

PairTradingState = Literal[
    "WATCHING",
    "QUALIFIED",
    "ENTRY_SIGNAL",
    "OPEN",
    "EXIT_SIGNAL",
    "CLOSED",
    "REJECTED",
]

PairLeggingPolicy = Literal["immediate_flatten", "retry_hedge"]
SpreadDirection = Literal["flat", "long_spread", "short_spread"]


class PairStateManager:
    """
    Robust state machine for two-asset pair trading lifecycles.

    States:
      - WATCHING: Waiting for sufficient historical bars / warm-up.
      - QUALIFIED: Cointegration confirmed; ready to receive entry signals.
      - ENTRY_SIGNAL: Entry threshold breached; sizing computed, awaiting fill.
      - OPEN: Both legs active and tracked.
      - EXIT_SIGNAL: Reversion, stop-loss, or qualification-loss exit requested.
      - CLOSED: Position flat; ready for next cycle.
      - REJECTED: Cointegration broken, legging failure, or disqualified.
    """

    def __init__(
        self,
        *,
        initial_state: PairTradingState = "WATCHING",
        qualification_status: str = "qualified",
        legging_policy: PairLeggingPolicy = "immediate_flatten",
    ) -> None:
        self.state: PairTradingState = initial_state
        self.qualification_status: str = qualification_status
        self.legging_policy: PairLeggingPolicy = legging_policy
        self.active_direction: SpreadDirection = "flat"
        self.holding_bars: int = 0
        self.exit_reason: str = ""
        self.last_rejection_reason: str = ""

    def reset(self) -> None:
        self.state = "WATCHING"
        self.active_direction = "flat"
        self.holding_bars = 0
        self.exit_reason = ""
        self.last_rejection_reason = ""

    def update_qualification(self, qualification_status: str) -> None:
        self.qualification_status = qualification_status
        if qualification_status == "rejected":
            if self.state == "OPEN":
                self.trigger_exit(reason="qualification_lost")
            elif self.state in ("WATCHING", "QUALIFIED", "ENTRY_SIGNAL"):
                self.state = "REJECTED"
                self.last_rejection_reason = "cointegration_qualification_lost"

    def on_bar(self, bar_count: int, lookback_period: int) -> None:
        if self.state == "OPEN":
            self.holding_bars += 1

        if self.state == "WATCHING":
            if bar_count >= lookback_period:
                if self.qualification_status == "rejected":
                    self.state = "REJECTED"
                    self.last_rejection_reason = "cointegration_rejected"
                else:
                    self.state = "QUALIFIED"

    def can_enter(self) -> bool:
        if self.qualification_status == "rejected":
            return False
        return self.state in ("QUALIFIED", "CLOSED")

    def trigger_entry(self, direction: Literal["long_spread", "short_spread"]) -> bool:
        """Attempt to trigger entry. Prevents duplicate entries when already in signal or open."""
        if not self.can_enter():
            return False
        self.state = "ENTRY_SIGNAL"
        self.active_direction = direction
        return True

    def confirm_entry_filled(
        self,
        leg_a_filled: bool,
        leg_b_filled: bool,
    ) -> tuple[bool, str]:
        """
        Confirm order execution for both legs.
        Handles one-leg failures (legging risk) according to legging_policy.
        """
        if self.state != "ENTRY_SIGNAL":
            return False, f"invalid_state_{self.state}"

        if leg_a_filled and leg_b_filled:
            self.state = "OPEN"
            self.holding_bars = 0
            return True, "filled"

        # One-leg execution failure
        if leg_a_filled != leg_b_filled:
            failed_leg = "leg_b" if leg_a_filled else "leg_a"
            if self.legging_policy == "immediate_flatten":
                self.state = "REJECTED"
                self.active_direction = "flat"
                self.last_rejection_reason = f"legging_failure_{failed_leg}_flattened"
                return False, self.last_rejection_reason
            return False, f"legging_failure_{failed_leg}_retry"

        # Neither leg filled
        self.state = "QUALIFIED" if self.qualification_status != "rejected" else "REJECTED"
        self.active_direction = "flat"
        return False, "both_legs_failed"

    def trigger_exit(self, reason: str = "reversion") -> bool:
        if self.state != "OPEN":
            return False
        self.state = "EXIT_SIGNAL"
        self.exit_reason = reason
        return True

    def confirm_exit_filled(self) -> None:
        self.active_direction = "flat"
        self.holding_bars = 0
        if self.qualification_status == "rejected":
            self.state = "REJECTED"
        else:
            self.state = "CLOSED"

