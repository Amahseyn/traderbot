from __future__ import annotations

import math
from typing import Sequence
import numpy as np
import pytest

from traderbot.analysis.cointegration import (
    CointegrationRegime,
    CointegrationScanner,
    CointegrationThresholds,
    QualificationStatus,
    StationarityStatus,
    augmented_dickey_fuller_test,
    benjamini_hochberg_correction,
    build_pair_trading_params,
    detect_structural_breaks,
    engle_granger_test,
    estimate_half_life,
    estimate_ols_hedge_ratio,
    rank_cointegrated_pairs,
    run_cointegrated_pair_backtest,
)


def _generate_bars_from_prices(
    prices: Sequence[float] | np.ndarray,
    symbol: str = "BTC",
    resolution: str = "60",
    start_timestamp: int = 1_000_000,
) -> list[dict]:
    step_seconds = int(resolution) * 60 if resolution.isdigit() else 3600
    bars = []
    for idx, price in enumerate(prices):
        p = float(price)
        bars.append({
            "symbol": symbol,
            "resolution": resolution,
            "timestamp": start_timestamp + idx * step_seconds,
            "open": p,
            "high": p * 1.002,
            "low": p * 0.998,
            "close": p,
            "volume": 1000.0,
        })
    return bars


# -----------------------------------------------------------------------------
# 1. Synthetic Cointegrated Random Walks
# -----------------------------------------------------------------------------

def test_cointegrated_random_walks():
    """
    Scenario 1: True cointegrated relationship.
    ln(P_B) is an I(1) random walk.
    ln(P_A) = alpha + beta * ln(P_B) + epsilon_t, where epsilon_t is stationary AR(1).
    Expect:
    - Cointegration p-value < 0.01
    - Stationarity status == 'stationary'
    - Hedge ratio close to true beta (1.5)
    - Valid half-life matching theoretical AR(1) formula
    - Qualification status == 'qualified'
    """
    np.random.seed(42)
    n = 250
    true_alpha = 0.5
    true_beta = 1.5
    true_phi = 0.60  # AR(1) coefficient for residual spread

    # Random walk for B
    innovations_b = np.random.normal(0, 0.01, size=n)
    log_p_b = 4.0 + np.cumsum(innovations_b)

    # Stationary AR(1) noise for spread
    spread_noise = np.zeros(n)
    for t in range(1, n):
        spread_noise[t] = true_phi * spread_noise[t - 1] + np.random.normal(0, 0.008)

    log_p_a = true_alpha + true_beta * log_p_b + spread_noise

    bars_a = _generate_bars_from_prices(np.exp(log_p_a), symbol="ASSET_A")
    bars_b = _generate_bars_from_prices(np.exp(log_p_b), symbol="ASSET_B")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            max_coint_pvalue=0.05,
            min_half_life_bars=1.0,
            max_half_life_bars=100.0,
            cost_buffer_multiplier=0.0,  # disable cost gate for pure statistical test
        )
    )

    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="ASSET_A", symbol_b="ASSET_B")

    assert res.cointegration_pvalue < 0.01
    assert res.adf_pvalue < 0.01
    assert res.stationarity_status == StationarityStatus.STATIONARY.value
    assert pytest.approx(res.hedge_ratio, abs=0.10) == true_beta
    assert pytest.approx(res.intercept, abs=0.40) == true_alpha

    # Theoretical half-life for phi=0.60: -ln(2)/ln(0.60) ~= 1.357 bars
    assert res.half_life_bars is not None
    assert 0.8 <= res.half_life_bars <= 3.0
    assert res.hedge_ratio_stability > 0.80
    assert res.structural_break_detected is False
    assert res.qualification_status == QualificationStatus.QUALIFIED.value
    assert len(res.rejection_reasons) == 0


# -----------------------------------------------------------------------------
# 2. Correlated but NON-Cointegrated Series (Spurious Regression)
# -----------------------------------------------------------------------------

def test_correlated_but_non_cointegrated_spurious():
    """
    Scenario 2: Spurious correlation.
    Two independent random walks with a shared upward deterministic trend.
    Pearson correlation is high (r > 0.85), but residuals have a unit root.
    Expect:
    - Engle-Granger cointegration test fails (p > 0.10)
    - Residual spread is non-stationary
    - Qualification status == 'rejected'
    - Proves Pearson correlation does NOT imply cointegration!
    """
    np.random.seed(101)
    n = 200
    t = np.arange(n)

    # Independent random walks with positive drift
    rw_a = np.cumsum(np.random.normal(0, 0.01, size=n))
    rw_b = np.cumsum(np.random.normal(0, 0.01, size=n))

    # Shared upward drift induces high Pearson correlation
    drift = 0.005 * t
    log_p_a = 4.0 + drift + rw_a
    log_p_b = 3.0 + drift + rw_b

    # Verify high correlation
    corr = np.corrcoef(np.diff(log_p_a), np.diff(log_p_b))[0, 1]
    # Price level correlation is very high
    level_corr = np.corrcoef(log_p_a, log_p_b)[0, 1]
    assert level_corr > 0.85

    bars_a = _generate_bars_from_prices(np.exp(log_p_a), symbol="SPURIOUS_A")
    bars_b = _generate_bars_from_prices(np.exp(log_p_b), symbol="SPURIOUS_B")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            max_coint_pvalue=0.05,
            cost_buffer_multiplier=0.0,
        )
    )

    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="SPURIOUS_A", symbol_b="SPURIOUS_B")

    # Cointegration should be rejected
    assert res.cointegration_pvalue > 0.05
    assert res.stationarity_status == StationarityStatus.NON_STATIONARY.value
    assert res.qualification_status == QualificationStatus.REJECTED.value
    assert any("cointegration_not_significant" in r for r in res.rejection_reasons)


# -----------------------------------------------------------------------------
# 3. Independent Random Walks
# -----------------------------------------------------------------------------

def test_independent_random_walks():
    """
    Scenario 3: Two completely independent Brownian motions.
    Expect:
    - Cointegration p-value >> 0.05
    - Stationarity status == 'non_stationary'
    - Status == 'rejected'
    """
    np.random.seed(202)
    n = 200
    log_p_a = 4.0 + np.cumsum(np.random.normal(0, 0.015, size=n))
    log_p_b = 4.0 + np.cumsum(np.random.normal(0, 0.015, size=n))

    bars_a = _generate_bars_from_prices(np.exp(log_p_a), symbol="IND_A")
    bars_b = _generate_bars_from_prices(np.exp(log_p_b), symbol="IND_B")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            max_coint_pvalue=0.05,
            cost_buffer_multiplier=0.0,
        )
    )

    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="IND_A", symbol_b="IND_B")

    assert res.cointegration_pvalue > 0.10
    assert res.qualification_status == QualificationStatus.REJECTED.value


# -----------------------------------------------------------------------------
# 4. Unstable Hedge Ratio
# -----------------------------------------------------------------------------

def test_unstable_hedge_ratio():
    """
    Scenario 4: Relationship where hedge ratio shifts dramatically midway
    (beta = 0.5 in first half, jumps to beta = 2.5 in second half).
    Expect:
    - Hedge ratio stability score is heavily penalized (< 0.50)
    - Structural break detected or status rejected for instability
    """
    np.random.seed(303)
    n = 240
    rw_b = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))
    log_p_b = rw_b

    # First half: beta = 0.5
    # Second half: beta = 2.5
    log_p_a = np.zeros(n)
    log_p_a[:120] = 1.0 + 0.5 * rw_b[:120] + np.random.normal(0, 0.005, size=120)
    log_p_a[120:] = 1.0 + 2.5 * rw_b[120:] + np.random.normal(0, 0.005, size=120)

    bars_a = _generate_bars_from_prices(np.exp(log_p_a), symbol="UNSTABLE_A")
    bars_b = _generate_bars_from_prices(np.exp(log_p_b), symbol="UNSTABLE_B")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            min_hedge_ratio_stability=0.60,
            cost_buffer_multiplier=0.0,
        )
    )

    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="UNSTABLE_A", symbol_b="UNSTABLE_B")

    assert res.hedge_ratio_stability < 0.50
    assert res.qualification_status == QualificationStatus.REJECTED.value
    assert (
        any("unstable_hedge_ratio" in r for r in res.rejection_reasons)
        or res.structural_break_detected
    )


# -----------------------------------------------------------------------------
# 5. Structural Break Detection (Chow Test)
# -----------------------------------------------------------------------------

def test_structural_break_detection():
    """
    Scenario 5: Cointegrated pair with a severe level jump midway (+10 standard deviations).
    Expect:
    - Chow structural break test triggers (p < 0.01)
    - structural_break_detected == True
    - CointegrationRegime == BREAKDOWN
    """
    np.random.seed(404)
    n = 200
    rw_b = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))
    log_p_b = rw_b

    spread_noise = np.zeros(n)
    for t in range(1, n):
        spread_noise[t] = 0.5 * spread_noise[t - 1] + np.random.normal(0, 0.005)

    # Permanent intercept jump at t = 120
    log_p_a = 0.5 + 1.2 * rw_b + spread_noise
    log_p_a[120:] += 0.15  # massive 15% / ~30-sigma jump in crypto terms

    bars_a = _generate_bars_from_prices(np.exp(log_p_a), symbol="BREAK_A")
    bars_b = _generate_bars_from_prices(np.exp(log_p_b), symbol="BREAK_B")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            max_chow_break_pvalue=0.01,
            cost_buffer_multiplier=0.0,
        )
    )

    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="BREAK_A", symbol_b="BREAK_B")

    assert res.structural_break_detected is True
    assert res.chow_pvalue < 0.01
    assert res.regime == CointegrationRegime.BREAKDOWN
    assert res.qualification_status == QualificationStatus.REJECTED.value
    assert any("structural break" in r.lower() or "divergence" in r.lower() for r in res.rejection_reasons)


# -----------------------------------------------------------------------------
# 6. Non-Stationary Spread (Explosive / Unit Root)
# -----------------------------------------------------------------------------

def test_non_stationary_spread_and_invalid_half_life():
    """
    Scenario 6: Spread is an explosive autoregressive process (lambda >= 0).
    Expect:
    - estimate_half_life returns (None, lambda, False)
    - Half-life rejected as invalid/undefined
    - Qualification status == 'rejected'
    """
    # Explosive AR(1): s_t = 1.05 * s_{t-1} + e_t
    np.random.seed(505)
    n = 150
    spread = np.zeros(n)
    spread[0] = 0.01
    for t in range(1, n):
        spread[t] = 1.05 * spread[t - 1] + np.random.normal(0, 0.001)

    hl, lambda_param, is_valid = estimate_half_life(spread)
    assert is_valid is False
    assert hl is None
    assert lambda_param >= 0.0

    # Also test pure random walk spread
    rw_spread = np.cumsum(np.random.normal(0, 0.01, size=n))
    hl_rw, lambda_rw, is_valid_rw = estimate_half_life(rw_spread)
    # Unit root has lambda ~ 0
    assert is_valid_rw is False or (hl_rw is not None and hl_rw > 50.0)


# -----------------------------------------------------------------------------
# 7. Benjamini-Hochberg FDR Multiple Testing Correction
# -----------------------------------------------------------------------------

def test_benjamini_hochberg_fdr():
    """
    Scenario 7: Benjamini-Hochberg FDR correction.
    Given raw p-values, verify step-up adjusted p-values match the FDR definition.
    """
    raw_p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.060, 0.150, 0.200, 0.850, 0.990]
    m = len(raw_p)

    adj = benjamini_hochberg_correction(raw_p)

    assert len(adj) == m
    # Adjusted p-values must be monotonically non-decreasing for sorted raw p-values
    for i in range(len(adj) - 1):
        assert adj[i] <= adj[i + 1] + 1e-12
    # First p-value: 0.001 * 10 / 1 = 0.010
    assert pytest.approx(adj[0], abs=1e-4) == 0.010
    # Last p-value: 0.990 * 10 / 10 = 0.990
    assert pytest.approx(adj[-1], abs=1e-4) == 0.990

    # Test order preservation on unsorted input
    unsorted_p = [0.060, 0.001, 0.990, 0.008]
    adj_unsorted = benjamini_hochberg_correction(unsorted_p)
    assert len(adj_unsorted) == 4
    # The smallest raw p-value (index 1) must yield the smallest adjusted p-value
    assert adj_unsorted[1] < adj_unsorted[0] < adj_unsorted[2]


# -----------------------------------------------------------------------------
# 8. Pair Ranking & Discovery Interface
# -----------------------------------------------------------------------------

def test_pair_ranking():
    """
    Scenario 8: Rank cointegrated pairs.
    Verify qualified pairs are ranked above marginal and rejected pairs.
    """
    np.random.seed(606)
    n = 150
    rw = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))

    # Pair 1: Ideal cointegration (phi = 0.70)
    noise1 = np.zeros(n)
    for t in range(1, n):
        noise1[t] = 0.70 * noise1[t - 1] + np.random.normal(0, 0.005)
    bars_1a = _generate_bars_from_prices(np.exp(1.0 + 1.2 * rw + noise1), symbol="AAA")
    bars_1b = _generate_bars_from_prices(np.exp(rw), symbol="BBB")

    # Pair 2: Independent (no cointegration)
    rw2 = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))
    bars_2a = _generate_bars_from_prices(np.exp(rw2), symbol="CCC")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            min_half_life_bars=1.0,
            cost_buffer_multiplier=0.0,
        )
    )

    universe = {
        "AAA": bars_1a,
        "BBB": bars_1b,
        "CCC": bars_2a,
    }

    scan_results = scanner.scan_universe(universe)
    assert len(scan_results) == 3  # (AAA,BBB), (AAA,CCC), (BBB,CCC)

    ranked = rank_cointegrated_pairs(scan_results)
    # The cointegrated pair (AAA, BBB) must rank #1
    top_pair = ranked[0]
    assert (top_pair.symbol_a, top_pair.symbol_b) == ("AAA", "BBB")
    assert top_pair.qualification_status == QualificationStatus.QUALIFIED.value


# -----------------------------------------------------------------------------
# 9. Backtest Adapter Integration
# -----------------------------------------------------------------------------

def test_integration_with_pair_trading_backtest():
    """
    Scenario 9: Integration with Traderbot pair backtest engine.
    Extract params from CointegrationResult via build_pair_trading_params
    and execute run_cointegrated_pair_backtest without error.
    """
    np.random.seed(707)
    n = 200
    rw = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.75 * noise[t - 1] + np.random.normal(0, 0.005)

    bars_a = _generate_bars_from_prices(np.exp(1.0 + 1.1 * rw + noise), symbol="DOMINANT")
    bars_b = _generate_bars_from_prices(np.exp(rw), symbol="HEDGE")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(min_observations=100, cost_buffer_multiplier=0.0)
    )
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="DOMINANT", symbol_b="HEDGE")

    # Verify param mapping
    params = build_pair_trading_params(res)
    assert params["pair_hedge_ratio"] == res.hedge_ratio
    assert params["pair_lookback_period"] >= 10

    # Run backtest
    backtest_res = run_cointegrated_pair_backtest(
        res,
        bars_a,
        bars_b,
        exchange="hyperliquid",
        initial_cash=10_000.0,
    )

    assert backtest_res.initial_cash == 10_000.0
    assert len(backtest_res.equity_curve) > 0
    assert backtest_res.final_equity > 0


# -----------------------------------------------------------------------------
# 10. Verification of All 16 Required Output Fields & to_dict() Serialization
# -----------------------------------------------------------------------------

def test_all_sixteen_output_fields_and_serialization():
    """
    Scenario 10: Verify all 16 required output fields from Section 7 exist,
    match expected types, and serialize cleanly to dictionary format.
    """
    np.random.seed(808)
    n = 120
    rw = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.65 * noise[t - 1] + np.random.normal(0, 0.005)

    bars_a = _generate_bars_from_prices(np.exp(0.5 + 1.2 * rw + noise), symbol="BTC")
    bars_b = _generate_bars_from_prices(np.exp(rw), symbol="ETH")

    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(min_observations=100, min_half_life_bars=1.0, cost_buffer_multiplier=0.0)
    )
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="BTC", symbol_b="ETH", timeframe="60")

    # 16 standard fields
    assert isinstance(res.symbol_a, str)
    assert isinstance(res.symbol_b, str)
    assert isinstance(res.timeframe, str)
    assert isinstance(res.hedge_ratio, float)
    assert isinstance(res.intercept, float)
    assert isinstance(res.adf_statistic, float)
    assert isinstance(res.adf_pvalue, float)
    assert isinstance(res.cointegration_pvalue, float)
    assert res.adjusted_pvalue is None or isinstance(res.adjusted_pvalue, float)
    assert isinstance(res.spread_mean, float)
    assert isinstance(res.spread_std, float)
    assert res.half_life_bars is None or isinstance(res.half_life_bars, float)
    assert isinstance(res.hedge_ratio_stability, float)
    assert isinstance(res.stationarity_status, str)
    assert isinstance(res.qualification_status, str)
    assert isinstance(res.rejection_reasons, list)

    # to_dict() serialization
    data = res.to_dict()
    assert data["symbol_a"] == "BTC"
    assert data["symbol_b"] == "ETH"
    assert "hedge_ratio" in data
    assert "adf_statistic" in data
    assert "cointegration_pvalue" in data
    assert "half_life_bars" in data
    assert "qualification_status" in data
    assert "rejection_reasons" in data


# -----------------------------------------------------------------------------
# 11. Insufficient Observations & Cost Headroom Rejections
# -----------------------------------------------------------------------------

def test_insufficient_observations_rejection():
    """
    Scenario 11: Candidate series shorter than min_observations.
    Expect immediate rejection with reason 'insufficient_observations'.
    """
    bars_a = _generate_bars_from_prices([100.0 + i for i in range(40)], symbol="SHORT_A")
    bars_b = _generate_bars_from_prices([100.0 + i for i in range(40)], symbol="SHORT_B")

    scanner = CointegrationScanner(thresholds=CointegrationThresholds(min_observations=100))
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="SHORT_A", symbol_b="SHORT_B")

    assert res.qualification_status == QualificationStatus.REJECTED.value
    assert any("insufficient_observations" in r for r in res.rejection_reasons)


def test_transaction_cost_headroom_gate():
    """
    Scenario 12: Cointegrated pair whose spread variance is tiny relative
    to exchange roundtrip trading fees.
    Expect: Rejected for insufficient cost headroom.
    """
    np.random.seed(909)
    n = 150
    rw = 4.0 + np.cumsum(np.random.normal(0, 0.01, size=n))
    # Extremely small noise: spread move is only 0.01%
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.70 * noise[t - 1] + np.random.normal(0, 0.0001)

    bars_a = _generate_bars_from_prices(np.exp(rw + noise), symbol="TIGHT_A")
    bars_b = _generate_bars_from_prices(np.exp(rw), symbol="TIGHT_B")

    # Hyperliquid fee is 0.0019 (0.19%). 1.5x buffer requires move > 0.285%
    scanner = CointegrationScanner(
        thresholds=CointegrationThresholds(
            min_observations=100,
            cost_buffer_multiplier=1.5,
            roundtrip_cost_pct=0.0019,
        )
    )
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="TIGHT_A", symbol_b="TIGHT_B")

    assert any("insufficient_cost_headroom" in r for r in res.rejection_reasons)

