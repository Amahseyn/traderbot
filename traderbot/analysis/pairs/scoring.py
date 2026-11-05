from __future__ import annotations

import math
from typing import Any

from traderbot.analysis.cointegration.models import (
    CointegrationResult,
    QualificationStatus,
)
from traderbot.analysis.pairs.models import (
    CandidatePair,
    PairQualityBreakdown,
    PairQualityWeights,
)
from traderbot.analysis.pairs.universe import MarketMetadata, compute_24h_quote_volume


def _safe_clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if not math.isfinite(value):
        return low
    return max(low, min(high, value))


class PairQualityScorer:
    """
    Multi-factor institutional quality scoring engine for cointegrated pairs.
    Normalizes statistical, stability, execution, and liquidity metrics into a bounded 0-100 score.
    Enforces hard rejection rules prior to ranking.
    """

    def __init__(self, weights: PairQualityWeights | None = None) -> None:
        self.weights = weights or PairQualityWeights()

    def score_pair(
        self,
        candidate: CandidatePair,
        coint_result: CointegrationResult,
        bars_a: list[dict[str, Any]],
        bars_b: list[dict[str, Any]],
        meta_a: MarketMetadata | None = None,
        meta_b: MarketMetadata | None = None,
        *,
        roundtrip_cost: float = 0.0019,  # Default 0.19% roundtrip
        target_volume_24h: float = 1_000_000.0,
        max_acceptable_spread_pct: float = 0.005,
    ) -> tuple[float, PairQualityBreakdown, list[str]]:
        """
        Compute normalized 0-100 score and breakdown.
        Returns:
            (total_score, breakdown, hard_rejection_reasons)
        """
        rejection_reasons = list(coint_result.rejection_reasons)

        # 1. Hard Rejection Verification
        is_hard_rejected = False
        if coint_result.qualification_status == QualificationStatus.REJECTED.value:
            is_hard_rejected = True

        if coint_result.half_life_bars is None or coint_result.half_life_bars <= 0:
            is_hard_rejected = True
            if "invalid_half_life" not in " ".join(rejection_reasons):
                rejection_reasons.append("invalid_half_life")

        if coint_result.structural_break_detected:
            is_hard_rejected = True
            if "structural_break" not in " ".join(rejection_reasons):
                rejection_reasons.append("structural_break_detected")

        # Zero score immediately if hard rejected
        if is_hard_rejected:
            breakdown = PairQualityBreakdown(
                cointegration_score=0.0,
                fdr_score=0.0,
                adf_score=0.0,
                half_life_score=0.0,
                hedge_ratio_stability_score=0.0,
                spread_stability_score=0.0,
                liquidity_score=0.0,
                bid_ask_spread_score=0.0,
                cost_headroom_score=0.0,
                total_score=0.0,
            )
            return 0.0, breakdown, rejection_reasons

        # 2. Sub-Score 1: Cointegration Significance (0.0 to 1.0)
        # Scaled relative to alpha = 0.05
        coint_p = coint_result.cointegration_pvalue
        s_coint = _safe_clip(1.0 - (coint_p / 0.05))

        # 3. Sub-Score 2: FDR Adjusted Significance (0.0 to 1.0)
        adj_p = coint_result.adjusted_pvalue if coint_result.adjusted_pvalue is not None else coint_p
        s_fdr = _safe_clip(1.0 - (adj_p / 0.10))

        # 4. Sub-Score 3: ADF Stationarity Margin (0.0 to 1.0)
        # Bounded distance beyond 5% critical value (-3.34)
        adf_p = coint_result.adf_pvalue
        s_adf = _safe_clip(1.0 - (adf_p / 0.05))

        # 5. Sub-Score 4: Half-Life Suitability (Gaussian bell curve peaking at optimal_half_life_bars)
        hl = coint_result.half_life_bars
        if hl is not None and hl > 0:
            s_hl = math.exp(-0.5 * (((hl - self.weights.optimal_half_life_bars) / 10.0) ** 2))
        else:
            s_hl = 0.0
        s_hl = _safe_clip(s_hl)

        # 6. Sub-Score 5: Hedge Ratio Stability (0.0 to 1.0)
        s_beta = _safe_clip(coint_result.hedge_ratio_stability)

        # 7. Sub-Score 6: Spread Stability (variance drift & regime)
        if coint_result.regime.value == "stable":
            s_spread_stab = 1.0
        elif coint_result.regime.value == "weakening":
            s_spread_stab = 0.50
        elif coint_result.regime.value == "regime_shift":
            s_spread_stab = 0.25
        else:
            s_spread_stab = 0.0

        # 8. Sub-Score 7: Liquidity & Trading Volume (Harmonic mean of 24h quote volumes)
        vol_a = compute_24h_quote_volume(bars_a)
        vol_b = compute_24h_quote_volume(bars_b)
        if vol_a > 0 and vol_b > 0:
            harmonic_vol = 2.0 * (vol_a * vol_b) / (vol_a + vol_b)
            s_liq = _safe_clip(harmonic_vol / target_volume_24h)
        else:
            s_liq = 0.0

        # 9. Sub-Score 8: Bid-Ask Spread Impact
        spread_a = meta_a.bid_ask_spread_pct if meta_a and meta_a.bid_ask_spread_pct is not None else 0.0005
        spread_b = meta_b.bid_ask_spread_pct if meta_b and meta_b.bid_ask_spread_pct is not None else 0.0005
        avg_spread = (spread_a + spread_b) / 2.0
        s_spread_cost = _safe_clip(1.0 - (avg_spread / max_acceptable_spread_pct))

        # 10. Sub-Score 9: Transaction Cost Headroom (Expected Move 2*spread_std vs Roundtrip Friction)
        expected_move = 2.0 * coint_result.spread_std
        if roundtrip_cost > 0:
            # 3x friction buffer is 100% score
            s_headroom = _safe_clip(expected_move / (3.0 * roundtrip_cost))
        else:
            s_headroom = 1.0

        # Total Weighted Composite Score (Scaled to 0 - 100)
        w = self.weights
        total_normalized = (
            w.cointegration_weight * s_coint
            + w.fdr_weight * s_fdr
            + w.adf_weight * s_adf
            + w.half_life_weight * s_hl
            + w.hedge_ratio_stability_weight * s_beta
            + w.spread_stability_weight * s_spread_stab
            + w.liquidity_weight * s_liq
            + w.bid_ask_spread_weight * s_spread_cost
            + w.cost_headroom_weight * s_headroom
        )

        total_score = round(max(0.0, min(100.0, total_normalized * 100.0)), 2)

        breakdown = PairQualityBreakdown(
            cointegration_score=round(s_coint * 100.0, 2),
            fdr_score=round(s_fdr * 100.0, 2),
            adf_score=round(s_adf * 100.0, 2),
            half_life_score=round(s_hl * 100.0, 2),
            hedge_ratio_stability_score=round(s_beta * 100.0, 2),
            spread_stability_score=round(s_spread_stab * 100.0, 2),
            liquidity_score=round(s_liq * 100.0, 2),
            bid_ask_spread_score=round(s_spread_cost * 100.0, 2),
            cost_headroom_score=round(s_headroom * 100.0, 2),
            total_score=total_score,
        )

        return total_score, breakdown, rejection_reasons

