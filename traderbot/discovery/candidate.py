from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    exchange: str
    symbol_key: str
    market_symbol: str
    resolution: str
    strategy_id: str
    params_source: str


@dataclass(slots=True)
class CandidateEvaluation:
    candidate: DiscoveryCandidate
    regime_label: str
    metrics: dict[str, Any]
    walk_forward_stability: float | None
    liquidity_score: float | None
    data_quality: dict[str, Any]
    rejection_reason: str | None = None
    component_scores: dict[str, float] | None = None
    composite_score: float | None = None
