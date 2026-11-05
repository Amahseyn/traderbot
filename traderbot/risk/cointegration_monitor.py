from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Sequence

import numpy as np

from traderbot.analysis.cointegration.statistical import (
    augmented_dickey_fuller_test,
    compute_rolling_hedge_ratio,
    detect_structural_breaks,
    estimate_half_life,
    mackinnon_coint_pvalue,
)


@dataclass(frozen=True, slots=True)
class CointegrationHealthReport:
    """Diagnostic health assessment of a live pair's statistical relationship."""

    status: str  # 'HEALTHY', 'DEGRADED', 'BROKEN'
    is_broken: bool
    recommended_action: str  # 'MAINTAIN', 'TIGHTEN_STOPS', 'SCALE_DOWN', 'EMERGENCY_FLATTEN'
    reasons: list[str] = field(default_factory=list)
    cointegration_pvalue: float = 1.0
    half_life_bars: float | None = None
    beta_stability_score: float = 1.0
    volatility_expansion_ratio: float = 1.0
    has_structural_break: bool = False


class CointegrationHealthMonitor:
    """
    Real-time monitor tracking statistical relationship degradation during pair trading:
    1. Cointegration breakdown (MacKinnon finite-sample residual unit root test).
    2. Hedge ratio instability (rolling OLS beta stability score & sign flips).
    3. Spread volatility expansion (current rolling variance vs baseline entry variance).
    4. Half-life deterioration (mean-reversion speed slowdown or non-reverting kappa).
    5. Structural breaks (split-sample Chow F-test & spread divergence).
    """

    def __init__(
        self,
        *,
        max_coint_pvalue: float = 0.10,
        min_beta_stability: float = 0.50,
        max_vol_expansion: float = 2.0,
        max_half_life_multiple: float = 3.0,
        chow_significance: float = 0.01,
        min_observations: int = 30,
    ) -> None:
        self.max_coint_pvalue = max_coint_pvalue
        self.min_beta_stability = min_beta_stability
        self.max_vol_expansion = max_vol_expansion
        self.max_half_life_multiple = max_half_life_multiple
        self.chow_significance = chow_significance
        self.min_observations = min_observations

    def evaluate_pair_health(
        self,
        prices_a: Sequence[float] | np.ndarray,
        prices_b: Sequence[float] | np.ndarray,
        *,
        hedge_ratio: float = 1.0,
        entry_spread_std: float | None = None,
        initial_half_life: float | None = None,
    ) -> CointegrationHealthReport:
        arr_a = np.asarray(prices_a, dtype=float)
        arr_b = np.asarray(prices_b, dtype=float)
        n = min(len(arr_a), len(arr_b))

        if n < self.min_observations:
            return CointegrationHealthReport(
                status="HEALTHY",
                is_broken=False,
                recommended_action="MAINTAIN",
                reasons=[],
            )

        sub_a = arr_a[-n:]
        sub_b = arr_b[-n:]

        if np.any(sub_a <= 0) or np.any(sub_b <= 0):
            return CointegrationHealthReport(
                status="BROKEN",
                is_broken=True,
                recommended_action="EMERGENCY_FLATTEN",
                reasons=["Non-positive prices encountered in series"],
            )

        log_a = np.log(sub_a)
        log_b = np.log(sub_b)

        # 1. Spread calculation using theoretical hedge ratio
        spread = log_a - hedge_ratio * log_b
        current_spread_std = float(np.std(spread, ddof=1)) if len(spread) > 1 else float(np.std(spread))

        # 2. Cointegration unit-root test on residuals
        adf_stat, _, _ = augmented_dickey_fuller_test(spread, max_lag=2, include_constant=True)
        coint_pvalue = mackinnon_coint_pvalue(adf_stat, n_obs=n)

        # 3. Rolling hedge ratio stability
        window = max(20, n // 3)
        timestamps = list(range(n))
        _, stability_score = compute_rolling_hedge_ratio(
            log_a,
            log_b,
            timestamps,
            window_bars=window,
            step_bars=max(1, window // 4),
        )

        # 4. Half-life calculation
        half_life, _, is_half_life_valid = estimate_half_life(spread)

        # 5. Structural break detection (Chow test + mean divergence)
        has_break, _, _, break_notes = detect_structural_breaks(
            log_a,
            log_b,
            spread,
            chow_significance=self.chow_significance,
        )

        reasons: list[str] = []
        is_broken = False
        is_degraded = False

        # Evaluate Cointegration Breakdown
        if coint_pvalue > self.max_coint_pvalue:
            is_broken = True
            reasons.append(
                f"Cointegration breakdown detected (ADF stat={adf_stat:.2f}, p={coint_pvalue:.4f} > {self.max_coint_pvalue})"
            )

        # Evaluate Structural Breaks
        if has_break:
            is_broken = True
            reasons.extend(break_notes)

        # Evaluate Hedge Ratio Instability
        if stability_score < self.min_beta_stability:
            is_degraded = True
            reasons.append(
                f"Hedge ratio instability detected (stability={stability_score:.2f} < {self.min_beta_stability})"
            )

        # Evaluate Volatility Expansion
        vol_expansion_ratio = 1.0
        if entry_spread_std is not None and entry_spread_std > 1e-12:
            vol_expansion_ratio = current_spread_std / entry_spread_std
            if vol_expansion_ratio > self.max_vol_expansion:
                is_degraded = True
                reasons.append(
                    f"Spread volatility expanded ({vol_expansion_ratio:.2f}x > {self.max_vol_expansion}x baseline)"
                )

        # Evaluate Half-Life Deterioration
        if not is_half_life_valid or half_life is None:
            is_degraded = True
            reasons.append("Half-life non-reverting")
        elif initial_half_life is not None and initial_half_life > 0:
            if half_life > (initial_half_life * self.max_half_life_multiple):
                is_degraded = True
                reasons.append(
                    f"Half-life deteriorated ({half_life:.1f} bars > {self.max_half_life_multiple}x initial {initial_half_life:.1f})"
                )

        # Determine Final Status & Recommended Action
        if is_broken:
            status = "BROKEN"
            recommended_action = "EMERGENCY_FLATTEN"
        elif is_degraded:
            status = "DEGRADED"
            recommended_action = "SCALE_DOWN"
        else:
            status = "HEALTHY"
            recommended_action = "MAINTAIN"

        return CointegrationHealthReport(
            status=status,
            is_broken=is_broken,
            recommended_action=recommended_action,
            reasons=reasons,
            cointegration_pvalue=coint_pvalue,
            half_life_bars=half_life,
            beta_stability_score=stability_score,
            volatility_expansion_ratio=vol_expansion_ratio,
            has_structural_break=has_break,
        )
