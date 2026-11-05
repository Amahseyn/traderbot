from __future__ import annotations

from traderbot.analysis.correlation.aligner import AlignedReturnSeries, align_candles_for_correlation
from traderbot.analysis.correlation.matrix import compute_correlation_matrix
from traderbot.analysis.correlation.metrics import (
    analyze_regime_and_breakdown,
    calculate_correlation_stability,
    classify_correlation,
    compute_rolling_correlation,
    pearson_correlation,
    spearman_correlation,
)
from traderbot.analysis.correlation.models import (
    CorrelationClassification,
    CorrelationMatrixResult,
    CorrelationRegimeAnalysis,
    CorrelationResult,
    DataQualityReport,
    RollingCorrelationPoint,
)
from traderbot.analysis.correlation.scanner import (
    SUPPORTED_TIMEFRAMES,
    CorrelationScanner,
    horizon_to_observation_bars,
)

__all__ = [
    "AlignedReturnSeries",
    "CorrelationClassification",
    "CorrelationMatrixResult",
    "CorrelationRegimeAnalysis",
    "CorrelationResult",
    "CorrelationScanner",
    "DataQualityReport",
    "RollingCorrelationPoint",
    "SUPPORTED_TIMEFRAMES",
    "align_candles_for_correlation",
    "analyze_regime_and_breakdown",
    "calculate_correlation_stability",
    "classify_correlation",
    "compute_correlation_matrix",
    "compute_rolling_correlation",
    "horizon_to_observation_bars",
    "pearson_correlation",
    "spearman_correlation",
]

