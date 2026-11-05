from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PairQualificationStatus(str, Enum):
    QUALIFIED = "qualified"
    MARGINAL = "marginal"
    REJECTED = "rejected"


class CandidateCategory(str, Enum):
    STRONG_POSITIVE = "strong_positive"
    STRONG_NEGATIVE = "strong_negative"
    WEAK_SCREENED = "weak_screened"


class RankChangeType(str, Enum):
    NEW_ENTRY = "new_entry"
    PROMOTION = "promotion"
    DEMOTION = "demotion"
    EXIT = "exit"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class MarketUniverseFilter:
    min_history_bars: int = 100
    min_volume_quote_24h: float = 50_000.0
    max_bid_ask_spread_pct: float = 0.005  # 0.50%
    min_order_book_depth_usd: float = 10_000.0
    filter_delisted: bool = True
    filter_inactive: bool = True
    max_symbols: int = 50


@dataclass(frozen=True, slots=True)
class CandidatePairCriteria:
    strong_pos_threshold: float = 0.70
    strong_neg_threshold: float = -0.70
    max_candidates: int | None = 100
    allow_weak_cointegrated: bool = True


@dataclass(frozen=True, slots=True)
class CandidatePair:
    pair_id: str
    symbol_a: str
    symbol_b: str
    correlation: float
    category: CandidateCategory
    observation_count: int


@dataclass(frozen=True, slots=True)
class PairQualityWeights:
    cointegration_weight: float = 0.20
    fdr_weight: float = 0.10
    adf_weight: float = 0.15
    half_life_weight: float = 0.15
    hedge_ratio_stability_weight: float = 0.15
    spread_stability_weight: float = 0.05
    liquidity_weight: float = 0.10
    bid_ask_spread_weight: float = 0.05
    cost_headroom_weight: float = 0.05
    optimal_half_life_bars: float = 15.0


@dataclass(frozen=True, slots=True)
class PairQualityBreakdown:
    cointegration_score: float
    fdr_score: float
    adf_score: float
    half_life_score: float
    hedge_ratio_stability_score: float
    spread_stability_score: float
    liquidity_score: float
    bid_ask_spread_score: float
    cost_headroom_score: float
    total_score: float


@dataclass(frozen=True, slots=True)
class DynamicRankingConfig:
    top_n: int = 10  # 5, 10, or 20
    hysteresis_delta: float = 5.0
    min_qualification_periods: int = 1
    diversity_spread_corr_max: float = 0.60
    max_pairs_per_symbol: int = 2


@dataclass(frozen=True, slots=True)
class RankTransition:
    pair_id: str
    previous_rank: int | None
    new_rank: int | None
    change_type: RankChangeType
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RankedPairResult:
    # 16 standard required output fields
    pair_id: str
    exchange: str
    symbol_a: str
    symbol_b: str
    timeframe: str
    correlation: float
    cointegration_status: str
    hedge_ratio: float
    half_life_bars: float | None
    liquidity_score: float
    stability_score: float
    pair_quality_score: float
    ranking_position: int | None
    qualification_status: str
    rejection_reasons: list[str] = field(default_factory=list)
    last_updated: int = 0

    # Diagnostic metadata
    cointegration_pvalue: float = 1.0
    adf_statistic: float = 0.0
    adjusted_pvalue: float | None = None
    spread_std: float = 0.0
    spread_mean: float = 0.0
    intercept: float = 0.0
    r_squared: float = 0.0
    score_breakdown: PairQualityBreakdown | None = None
    residual_spread: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "exchange": self.exchange,
            "symbol_a": self.symbol_a,
            "symbol_b": self.symbol_b,
            "timeframe": self.timeframe,
            "correlation": round(self.correlation, 4),
            "cointegration_status": self.cointegration_status,
            "hedge_ratio": round(self.hedge_ratio, 6),
            "intercept": round(self.intercept, 6),
            "half_life_bars": round(self.half_life_bars, 2) if self.half_life_bars is not None else None,
            "liquidity_score": round(self.liquidity_score, 2),
            "stability_score": round(self.stability_score, 2),
            "pair_quality_score": round(self.pair_quality_score, 2),
            "ranking_position": self.ranking_position,
            "qualification_status": self.qualification_status,
            "rejection_reasons": list(self.rejection_reasons),
            "last_updated": self.last_updated,
        }


@dataclass(frozen=True, slots=True)
class RankingSnapshot:
    snapshot_timestamp: int
    exchange: str
    timeframe: str
    ranked_pairs: list[RankedPairResult]
    qualification_history: dict[str, int] = field(default_factory=dict)

