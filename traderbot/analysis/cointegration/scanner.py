from __future__ import annotations

import time
from typing import Any

import numpy as np

from traderbot.analysis.cointegration.models import (
    CointegrationRegime,
    CointegrationResult,
    CointegrationThresholds,
    QualificationStatus,
    StationarityStatus,
)
from traderbot.analysis.cointegration.statistical import (
    augmented_dickey_fuller_test,
    benjamini_hochberg_correction,
    compute_rolling_hedge_ratio,
    detect_structural_breaks,
    engle_granger_test,
    estimate_half_life,
    estimate_ols_hedge_ratio,
)
from traderbot.analysis.correlation.aligner import align_candles_for_correlation
from traderbot.utils.trading_costs import roundtrip_cost_pct


class CointegrationScanner:
    """
    Institutional quantitative scanner for Engle-Granger cointegration,
    residual spread stationarity, Ornstein-Uhlenbeck half-life modeling,
    and multiple-testing false discovery control across cryptocurrency pairs.
    """

    def __init__(self, thresholds: CointegrationThresholds | None = None) -> None:
        self.thresholds = thresholds or CointegrationThresholds()

    def analyze_pair(
        self,
        bars_a: list[dict[str, Any]],
        bars_b: list[dict[str, Any]],
        *,
        symbol_a: str,
        symbol_b: str,
        timeframe: str = "60",
        roundtrip_cost: float | None = None,
    ) -> CointegrationResult:
        """
        Evaluate cointegration, spread stationarity, half-life, and parameter stability
        for a pair of cryptocurrency candle series.
        """
        now_ts = int(time.time())
        aligned = align_candles_for_correlation(
            bars_a,
            bars_b,
            resolution=timeframe,
            min_observations=10,
        )

        n_obs = len(aligned.closes_a)
        rejection_reasons: list[str] = []

        # Check sample size
        if n_obs < self.thresholds.min_observations:
            rejection_reasons.append(
                f"insufficient_observations ({n_obs} < {self.thresholds.min_observations})"
            )
            return CointegrationResult(
                symbol_a=symbol_a,
                symbol_b=symbol_b,
                timeframe=timeframe,
                hedge_ratio=0.0,
                intercept=0.0,
                adf_statistic=0.0,
                adf_pvalue=1.0,
                cointegration_pvalue=1.0,
                adjusted_pvalue=None,
                spread_mean=0.0,
                spread_std=0.0,
                half_life_bars=None,
                hedge_ratio_stability=0.0,
                stationarity_status=StationarityStatus.NON_STATIONARY.value,
                qualification_status=QualificationStatus.REJECTED.value,
                rejection_reasons=rejection_reasons,
                data_quality=aligned.quality_report,
                calculation_timestamp=now_ts,
            )

        # Log prices
        log_a = np.log(aligned.closes_a)
        log_b = np.log(aligned.closes_b)

        # 1. Engle-Granger Cointegration Test
        coint_stat, coint_pvalue, alpha, beta, spread, _ = engle_granger_test(log_a, log_b)

        # 2. Augmented Dickey-Fuller Test on residual spread
        adf_stat, adf_pvalue, _ = augmented_dickey_fuller_test(spread, include_constant=False)

        # 3. Half-Life via Ornstein-Uhlenbeck AR(1) model
        half_life_bars, lambda_param, is_valid_hl = estimate_half_life(spread)

        # 4. Rolling Hedge Ratio & Stability Analysis
        rolling_window = min(60, n_obs // 2) if n_obs >= 20 else n_obs
        step_bars = max(1, n_obs // 40)
        rolling_points, stability_score = compute_rolling_hedge_ratio(
            log_a,
            log_b,
            aligned.timestamps,
            window_bars=rolling_window,
            step_bars=step_bars,
        )

        # 5. Structural Break Detection (Chow Test & Mean Divergence)
        has_break, chow_stat, chow_pvalue, break_notes = detect_structural_breaks(
            log_a,
            log_b,
            spread,
            chow_significance=self.thresholds.max_chow_break_pvalue,
        )

        # 6. Spread Statistics & R-squared
        spread_mean = float(np.mean(spread))
        spread_std = float(np.std(spread))
        spread_var = float(np.var(spread))
        _, _, _, r_squared, _ = estimate_ols_hedge_ratio(log_a, log_b)

        # Evaluate Stationarity Status
        if coint_pvalue <= self.thresholds.max_coint_pvalue and adf_pvalue <= self.thresholds.max_adf_pvalue:
            stationarity_status = StationarityStatus.STATIONARY.value
        elif coint_pvalue <= 0.10:
            stationarity_status = StationarityStatus.TREND_STATIONARY.value
        else:
            stationarity_status = StationarityStatus.NON_STATIONARY.value

        # Qualification Criteria Verification
        if coint_pvalue > self.thresholds.max_coint_pvalue:
            rejection_reasons.append(
                f"cointegration_not_significant (p={coint_pvalue:.4f} > {self.thresholds.max_coint_pvalue})"
            )

        if adf_pvalue > self.thresholds.max_adf_pvalue:
            rejection_reasons.append(
                f"non_stationary_residuals (adf_p={adf_pvalue:.4f} > {self.thresholds.max_adf_pvalue})"
            )

        if not is_valid_hl or half_life_bars is None:
            rejection_reasons.append(
                f"invalid_half_life (lambda={lambda_param:.4f} >= 0, non-reverting)"
            )
        elif half_life_bars < self.thresholds.min_half_life_bars:
            rejection_reasons.append(
                f"half_life_too_short ({half_life_bars:.1f} < {self.thresholds.min_half_life_bars})"
            )
        elif half_life_bars > self.thresholds.max_half_life_bars:
            rejection_reasons.append(
                f"half_life_too_long ({half_life_bars:.1f} > {self.thresholds.max_half_life_bars})"
            )

        if stability_score < self.thresholds.min_hedge_ratio_stability:
            rejection_reasons.append(
                f"unstable_hedge_ratio (stability={stability_score:.2f} < {self.thresholds.min_hedge_ratio_stability:.2f})"
            )

        if has_break:
            rejection_reasons.extend(break_notes)

        if spread_var < self.thresholds.min_spread_variance:
            rejection_reasons.append(
                f"zero_spread_variance ({spread_var:.2e} < {self.thresholds.min_spread_variance:.2e})"
            )

        # Transaction cost buffer verification
        cost_pct = roundtrip_cost
        if cost_pct is None and self.thresholds.roundtrip_cost_pct is not None:
            cost_pct = self.thresholds.roundtrip_cost_pct
        if cost_pct is None:
            # Check default venue cost
            cost_pct = roundtrip_cost_pct(exchange="hyperliquid")

        if cost_pct is not None and cost_pct > 0.0:
            expected_move = 2.0 * spread_std
            required_move = self.thresholds.cost_buffer_multiplier * cost_pct
            if expected_move < required_move:
                rejection_reasons.append(
                    f"insufficient_cost_headroom (edge {expected_move * 100:.3f}% < required {required_move * 100:.3f}%)"
                )

        # Qualification Status
        if len(rejection_reasons) == 0:
            qualification_status = QualificationStatus.QUALIFIED.value
        elif (
            coint_pvalue <= self.thresholds.max_coint_pvalue
            and is_valid_hl
            and len(rejection_reasons) <= 2
            and not has_break
        ):
            qualification_status = QualificationStatus.MARGINAL.value
        else:
            qualification_status = QualificationStatus.REJECTED.value

        # Regime Status
        if has_break:
            regime = CointegrationRegime.BREAKDOWN
        elif stability_score < 0.50:
            regime = CointegrationRegime.REGIME_SHIFT
        elif coint_pvalue > self.thresholds.max_coint_pvalue and coint_pvalue <= 0.10:
            regime = CointegrationRegime.WEAKENING
        else:
            regime = CointegrationRegime.STABLE

        return CointegrationResult(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            timeframe=timeframe,
            hedge_ratio=float(beta),
            intercept=float(alpha),
            adf_statistic=float(adf_stat),
            adf_pvalue=float(adf_pvalue),
            cointegration_pvalue=float(coint_pvalue),
            adjusted_pvalue=None,
            spread_mean=spread_mean,
            spread_std=spread_std,
            half_life_bars=half_life_bars,
            hedge_ratio_stability=stability_score,
            stationarity_status=stationarity_status,
            qualification_status=qualification_status,
            rejection_reasons=rejection_reasons,
            r_squared=float(r_squared),
            chow_statistic=float(chow_stat),
            chow_pvalue=float(chow_pvalue),
            structural_break_detected=has_break,
            regime=regime,
            rolling_hedge_ratios=rolling_points,
            data_quality=aligned.quality_report,
            calculation_timestamp=now_ts,
        )

    def scan_universe(
        self,
        bars_by_symbol: dict[str, list[dict[str, Any]]],
        *,
        timeframe: str = "60",
        roundtrip_cost: float | None = None,
    ) -> list[CointegrationResult]:
        """
        Scan all pairwise combinations in a multi-asset universe and apply
        Benjamini-Hochberg FDR correction across candidate pairs.
        """
        symbols = sorted(bars_by_symbol.keys())
        raw_results: list[CointegrationResult] = []

        for idx_a in range(len(symbols)):
            for idx_b in range(idx_a + 1, len(symbols)):
                sym_a = symbols[idx_a]
                sym_b = symbols[idx_b]
                res = self.analyze_pair(
                    bars_by_symbol[sym_a],
                    bars_by_symbol[sym_b],
                    symbol_a=sym_a,
                    symbol_b=sym_b,
                    timeframe=timeframe,
                    roundtrip_cost=roundtrip_cost,
                )
                raw_results.append(res)

        if not raw_results:
            return []

        # Apply Benjamini-Hochberg correction
        p_values = [r.cointegration_pvalue for r in raw_results]
        adjusted_p_values = benjamini_hochberg_correction(p_values)

        final_results: list[CointegrationResult] = []
        for res, adj_p in zip(raw_results, adjusted_p_values):
            reasons = list(res.rejection_reasons)
            status = res.qualification_status

            if adj_p > self.thresholds.max_fdr_pvalue:
                if status == QualificationStatus.QUALIFIED.value:
                    status = QualificationStatus.REJECTED.value
                    reasons.append(
                        f"fdr_rejected (adjusted_p={adj_p:.4f} > {self.thresholds.max_fdr_pvalue})"
                    )

            final_results.append(CointegrationResult(
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
            ))

        return final_results
