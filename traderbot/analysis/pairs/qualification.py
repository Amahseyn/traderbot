from __future__ import annotations

import time
from typing import Any

from traderbot.analysis.cointegration.models import (
    CointegrationResult,
    CointegrationThresholds,
    QualificationStatus,
)
from traderbot.analysis.cointegration.scanner import CointegrationScanner
from traderbot.analysis.cointegration.statistical import benjamini_hochberg_correction
from traderbot.analysis.pairs.models import CandidatePair, PairQualificationStatus
from traderbot.utils.trading_costs import roundtrip_cost_pct


class CointegrationQualifier:
    """
    Statistical cointegration qualification engine.
    Executes Engle-Granger tests, MacKinnon finite-sample response surfaces,
    ADF stationarity, Ornstein-Uhlenbeck half-life validation, structural break detection,
    and Benjamini-Hochberg False Discovery Rate (FDR) control across candidate pairs.
    """

    def __init__(
        self,
        thresholds: CointegrationThresholds | None = None,
        cointegration_scanner: CointegrationScanner | None = None,
    ) -> None:
        self.thresholds = thresholds or CointegrationThresholds()
        self.scanner = cointegration_scanner or CointegrationScanner(thresholds=self.thresholds)

    def qualify_candidates(
        self,
        candidates: list[CandidatePair],
        bars_by_symbol: dict[str, list[dict[str, Any]]],
        *,
        exchange: str = "hyperliquid",
        timeframe: str = "60",
        roundtrip_cost: float | None = None,
    ) -> dict[str, CointegrationResult]:
        """
        Evaluate candidate pairs and return cointegration results keyed by pair_id.
        Applies Benjamini-Hochberg FDR correction across the candidate batch.
        """
        if not candidates:
            return {}

        cost = roundtrip_cost
        if cost is None and self.thresholds.roundtrip_cost_pct is not None:
            cost = self.thresholds.roundtrip_cost_pct
        if cost is None:
            cost = roundtrip_cost_pct(exchange=exchange)

        raw_results: list[tuple[CandidatePair, CointegrationResult]] = []
        for cand in candidates:
            bars_a = bars_by_symbol.get(cand.symbol_a, [])
            bars_b = bars_by_symbol.get(cand.symbol_b, [])

            result = self.scanner.analyze_pair(
                bars_a,
                bars_b,
                symbol_a=cand.symbol_a,
                symbol_b=cand.symbol_b,
                timeframe=timeframe,
                roundtrip_cost=cost,
            )
            raw_results.append((cand, result))

        # Multiple testing FDR correction across candidate batch
        p_values = [res.cointegration_pvalue for _, res in raw_results]
        adjusted_p_values = benjamini_hochberg_correction(p_values)

        qualified_map: dict[str, CointegrationResult] = {}
        for (cand, res), adj_p in zip(raw_results, adjusted_p_values):
            reasons = list(res.rejection_reasons)
            status = res.qualification_status

            if adj_p > self.thresholds.max_fdr_pvalue:
                if status == QualificationStatus.QUALIFIED.value:
                    status = QualificationStatus.REJECTED.value
                    reasons.append(
                        f"fdr_rejected (adjusted_p={adj_p:.4f} > {self.thresholds.max_fdr_pvalue})"
                    )

            final_result = CointegrationResult(
                symbol_a=res.symbol_a,
                symbol_b=res.symbol_b,
                timeframe=res.timeframe,
                hedge_ratio=res.hedge_ratio,
                intercept=res.intercept,
                adf_statistic=res.adf_statistic,
                adf_pvalue=res.adf_pvalue,
                cointegration_pvalue=res.cointegration_pvalue,
                adjusted_pvalue=float(adj_p),
                spread_mean=res.spread_mean,
                spread_std=res.spread_std,
                half_life_bars=res.half_life_bars,
                hedge_ratio_stability=res.hedge_ratio_stability,
                stationarity_status=res.stationarity_status,
                qualification_status=status,
                rejection_reasons=reasons,
                r_squared=res.r_squared,
                chow_statistic=res.chow_statistic,
                chow_pvalue=res.chow_pvalue,
                structural_break_detected=res.structural_break_detected,
                regime=res.regime,
                rolling_hedge_ratios=res.rolling_hedge_ratios,
                data_quality=res.data_quality,
                calculation_timestamp=res.calculation_timestamp,
            )
            qualified_map[cand.pair_id] = final_result

        return qualified_map

