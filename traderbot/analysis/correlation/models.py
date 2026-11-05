from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CorrelationClassification(str, Enum):
    STRONG_POSITIVE = "strong_positive"       # r >= 0.70
    MODERATE_POSITIVE = "moderate_positive"   # 0.30 <= r < 0.70
    NEUTRAL = "neutral"                       # -0.30 < r < 0.30
    MODERATE_NEGATIVE = "moderate_negative"   # -0.70 < r <= -0.30
    STRONG_NEGATIVE = "strong_negative"       # r <= -0.70


@dataclass(frozen=True, slots=True)
class RollingCorrelationPoint:
    timestamp: int
    pearson: float
    spearman: float


@dataclass(frozen=True, slots=True)
class CorrelationRegimeAnalysis:
    is_persistent_negative: bool
    breakdown_detected: bool
    regime_shift_detected: bool
    recent_mean_correlation: float
    historical_mean_correlation: float
    correlation_divergence: float


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    total_bars_a: int
    total_bars_b: int
    aligned_bars: int
    missing_bars_a: int
    missing_bars_b: int
    duplicate_timestamps_dropped: int
    zero_variance_detected: bool
    quality_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CorrelationResult:
    symbol_a: str
    symbol_b: str
    timeframe: str
    pearson: float
    spearman: float
    rolling_correlation: list[RollingCorrelationPoint]
    correlation_stability: float
    classification: CorrelationClassification
    observation_count: int
    calculation_timestamp: int
    regime_analysis: CorrelationRegimeAnalysis
    data_quality: DataQualityReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_a": self.symbol_a,
            "symbol_b": self.symbol_b,
            "timeframe": self.timeframe,
            "pearson": round(self.pearson, 4),
            "spearman": round(self.spearman, 4),
            "correlation_stability": round(self.correlation_stability, 4),
            "classification": self.classification.value,
            "observation_count": self.observation_count,
            "calculation_timestamp": self.calculation_timestamp,
            "is_persistent_negative": self.regime_analysis.is_persistent_negative,
            "breakdown_detected": self.regime_analysis.breakdown_detected,
            "rolling_correlation": [
                {"timestamp": pt.timestamp, "pearson": round(pt.pearson, 4), "spearman": round(pt.spearman, 4)}
                for pt in self.rolling_correlation
            ],
            "data_quality_notes": self.data_quality.quality_notes,
        }


@dataclass(frozen=True, slots=True)
class CorrelationMatrixResult:
    symbols: list[str]
    timeframe: str
    pearson_matrix: list[list[float]]
    spearman_matrix: list[list[float]]
    observation_matrix: list[list[int]]
    calculation_timestamp: int

