from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from traderbot.analysis.correlation.models import DataQualityReport


class StationarityStatus(str, Enum):
    STATIONARY = "stationary"
    TREND_STATIONARY = "trend_stationary"
    NON_STATIONARY = "non_stationary"


class QualificationStatus(str, Enum):
    QUALIFIED = "qualified"
    MARGINAL = "marginal"
    REJECTED = "rejected"


class CointegrationRegime(str, Enum):
    STABLE = "stable"
    WEAKENING = "weakening"
    BREAKDOWN = "breakdown"
    REGIME_SHIFT = "regime_shift"


@dataclass(frozen=True, slots=True)
class RollingHedgeRatioPoint:
    timestamp: int
    hedge_ratio: float
    intercept: float
    spread_std: float
    adf_statistic: float


@dataclass(frozen=True, slots=True)
class CointegrationThresholds:
    min_observations: int = 100
    max_coint_pvalue: float = 0.05
    max_adf_pvalue: float = 0.05
    max_fdr_pvalue: float = 0.10
    min_half_life_bars: float = 3.0
    max_half_life_bars: float = 120.0
    min_hedge_ratio_stability: float = 0.60
    max_chow_break_pvalue: float = 0.01
    min_spread_variance: float = 1e-8
    cost_buffer_multiplier: float = 1.5
    roundtrip_cost_pct: float | None = None
    min_volume: float = 0.0


@dataclass(frozen=True, slots=True)
class CointegrationResult:
    # 16 standard required output fields
    symbol_a: str
    symbol_b: str
    timeframe: str
    hedge_ratio: float
    intercept: float
    adf_statistic: float
    adf_pvalue: float
    cointegration_pvalue: float
    adjusted_pvalue: float | None
    spread_mean: float
    spread_std: float
    half_life_bars: float | None
    hedge_ratio_stability: float
    stationarity_status: str
    qualification_status: str
    rejection_reasons: list[str] = field(default_factory=list)

    # Supplementary econometric diagnostics
    r_squared: float = 0.0
    chow_statistic: float = 0.0
    chow_pvalue: float = 1.0
    structural_break_detected: bool = False
    regime: CointegrationRegime = CointegrationRegime.STABLE
    rolling_hedge_ratios: list[RollingHedgeRatioPoint] = field(default_factory=list)
    data_quality: DataQualityReport | None = None
    calculation_timestamp: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_a": self.symbol_a,
            "symbol_b": self.symbol_b,
            "timeframe": self.timeframe,
            "hedge_ratio": round(self.hedge_ratio, 6),
            "intercept": round(self.intercept, 6),
            "adf_statistic": round(self.adf_statistic, 4),
            "adf_pvalue": round(self.adf_pvalue, 6),
            "cointegration_pvalue": round(self.cointegration_pvalue, 6),
            "adjusted_pvalue": round(self.adjusted_pvalue, 6) if self.adjusted_pvalue is not None else None,
            "spread_mean": round(self.spread_mean, 6),
            "spread_std": round(self.spread_std, 6),
            "half_life_bars": round(self.half_life_bars, 2) if self.half_life_bars is not None else None,
            "hedge_ratio_stability": round(self.hedge_ratio_stability, 4),
            "stationarity_status": self.stationarity_status,
            "qualification_status": self.qualification_status,
            "rejection_reasons": list(self.rejection_reasons),
            "r_squared": round(self.r_squared, 4),
            "chow_statistic": round(self.chow_statistic, 4),
            "chow_pvalue": round(self.chow_pvalue, 6),
            "structural_break_detected": self.structural_break_detected,
            "regime": self.regime.value,
            "rolling_points_count": len(self.rolling_hedge_ratios),
            "calculation_timestamp": self.calculation_timestamp,
        }

