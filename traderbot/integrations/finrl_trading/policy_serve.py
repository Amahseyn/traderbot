"""
Frozen-policy serving hooks for future perp RL (checkpoint path + traderbot risk guardrails).

SB3/PPO training stays in FinRL-Trading or external jobs; traderbot loads a strategy id
or ONNX/checkpoint here and routes orders through ``terminal/`` + ``execution_cost_profile``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.registry import algorithm_for_id


@dataclass(frozen=True, slots=True)
class FrozenPolicySpec:
    """Describes a deployable policy artifact."""

    strategy_id: str
    checkpoint_path: Path | None = None
    kwargs: dict[str, Any] | None = None


def load_algorithm_from_policy(spec: FrozenPolicySpec) -> Algorithm:
    """
    Resolve a live/paper algorithm from a policy spec.

    When ``checkpoint_path`` is set, callers must wire a custom ``Algorithm`` subclass
    that loads weights; until then we fall back to the named rule-based strategy preset.
    """
    kwargs = dict(spec.kwargs or {})
    if spec.checkpoint_path is not None and not spec.checkpoint_path.is_file():
        raise FileNotFoundError(spec.checkpoint_path)
    return algorithm_for_id(spec.strategy_id, **kwargs)


def apply_risk_guardrails(
    signal: str,
    *,
    max_leverage: float = 1.0,
    current_leverage: float = 0.0,
    kill_switch: bool = False,
) -> str:
    """Clamp or flatten signals before ``terminal`` order sizing."""
    if kill_switch or max_leverage <= 0:
        return "sell" if current_leverage > 0 else "hold"
    if signal == "buy" and current_leverage >= max_leverage:
        return "hold"
    return signal


GuardrailFn = Callable[..., str]
