from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Holdout paper-account stepping (independent of forecast label horizon)."""

    horizon_bars: int
    bar_minutes: int
    hold_bars: int | None = None
    decision_bars: int = 1

    def resolved_hold_bars(self) -> int:
        hold = self.hold_bars if self.hold_bars is not None else self.horizon_bars
        if hold < 1:
            raise ValueError("hold_bars must be >= 1")
        return hold

    def resolved_decision_bars(self) -> int:
        if self.decision_bars < 1:
            raise ValueError("decision_bars must be >= 1")
        return self.decision_bars

    def to_dict(self) -> dict[str, int]:
        return {
            "horizon_bars": self.horizon_bars,
            "bar_minutes": self.bar_minutes,
            "sim_hold_bars": self.resolved_hold_bars(),
            "sim_decision_bars": self.resolved_decision_bars(),
        }


def simulation_config_from_horizon(
    *,
    horizon_bars: int,
    bar_minutes: int,
    sim_hold_bars: int | None = None,
    sim_decision_bars: int | None = None,
    sim_align_to_horizon = False,
) -> SimulationConfig:
    if sim_align_to_horizon:
        step = horizon_bars
        return SimulationConfig(
            horizon_bars=horizon_bars,
            bar_minutes=bar_minutes,
            hold_bars=step,
            decision_bars=step,
        )
    return SimulationConfig(
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        hold_bars=sim_hold_bars,
        decision_bars=sim_decision_bars if sim_decision_bars is not None else 1,
    )


def add_simulation_cli_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sim-hold-bars",
        type=int,
        default=None,
        help="Bars to wait after a long before next decision (default: same as --horizon-bars)",
    )
    parser.add_argument(
        "--sim-decision-bars",
        type=int,
        default=None,
        help="When flat, advance this many bars per simulation stage (default: 1)",
    )
    parser.add_argument(
        "--sim-align-to-horizon",
        action="store_true",
        help="Set sim hold and decision steps both to --horizon-bars (one stage per forecast window)",
    )


def simulation_config_from_namespace(
    args: argparse.Namespace,
    *,
    horizon_bars: int,
    bar_minutes: int,
) -> SimulationConfig:
    return simulation_config_from_horizon(
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        sim_hold_bars=getattr(args, "sim_hold_bars", None),
        sim_decision_bars=getattr(args, "sim_decision_bars", None),
        sim_align_to_horizon=getattr(args, "sim_align_to_horizon", False),
    )
