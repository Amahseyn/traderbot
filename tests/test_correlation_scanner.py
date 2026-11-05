from __future__ import annotations

import math
import numpy as np
import pytest

from traderbot.analysis.correlation import (
    CorrelationClassification,
    CorrelationScanner,
    compute_correlation_matrix,
    horizon_to_observation_bars,
    pearson_correlation,
    spearman_correlation,
)


def _generate_bars_from_returns(returns: list[float], start_price: float = 100.0, symbol: str = "BTC") -> list[dict]:
    bars = []
    current_price = start_price
    # Bar 0 is base
    bars.append({
        "symbol": symbol,
        "resolution": "60",
        "timestamp": 0,
        "open": current_price,
        "high": current_price * 1.002,
        "low": current_price * 0.998,
        "close": current_price,
        "volume": 100.0,
    })
    for idx, ret in enumerate(returns):
        current_price = current_price * math.exp(ret)
        bars.append({
            "symbol": symbol,
            "resolution": "60",
            "timestamp": (idx + 1) * 3600,
            "open": current_price,
            "high": current_price * 1.002,
            "low": current_price * 0.998,
            "close": current_price,
            "volume": 100.0,
        })
    return bars


def test_perfect_positive_correlation():
    """
    Scenario 1: Perfect positive correlation (r = +1.0, rho = +1.0).
    """
    base_returns = [0.01 * math.sin(i / 3.0) for i in range(60)]
    bars_a = _generate_bars_from_returns(base_returns, 100.0, "BTC")
    # Asset B moves proportionally: r_b = 2.0 * r_a
    bars_b = _generate_bars_from_returns([2.0 * r for r in base_returns], 50.0, "ETH")

    scanner = CorrelationScanner()
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="BTC", symbol_b="ETH", timeframe="60", window_horizon="24h")

    assert pytest.approx(res.pearson, abs=1e-4) == 1.0
    assert pytest.approx(res.spearman, abs=1e-4) == 1.0
    assert res.classification == CorrelationClassification.STRONG_POSITIVE
    assert res.correlation_stability < 1e-4
    assert res.observation_count == 60


def test_perfect_negative_correlation():
    """
    Scenario 2: Perfect negative correlation (r = -1.0, rho = -1.0).
    """
    base_returns = [0.01 * math.sin(i / 4.0) for i in range(80)]
    bars_a = _generate_bars_from_returns(base_returns, 100.0, "BTC")
    # Asset B moves in exact inverse: r_b = -1.5 * r_a
    bars_b = _generate_bars_from_returns([-1.5 * r for r in base_returns], 200.0, "INVERSE")

    scanner = CorrelationScanner()
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="BTC", symbol_b="INVERSE", timeframe="60", window_horizon="24h")

    assert pytest.approx(res.pearson, abs=1e-4) == -1.0
    assert pytest.approx(res.spearman, abs=1e-4) == -1.0
    assert res.classification == CorrelationClassification.STRONG_NEGATIVE
    assert res.regime_analysis.is_persistent_negative is True
    assert res.correlation_stability < 1e-4


def test_independent_orthogonal_assets():
    """
    Scenario 3: Independent / orthogonal assets (r ~ 0.0).
    """
    # Sinusoid and cosinusoid over complete cycles are orthogonal (inner product is 0)
    cycle = 32
    steps = cycle * 4  # 128 points
    ret_a = [0.02 * math.sin(2.0 * math.pi * i / cycle) for i in range(steps)]
    ret_b = [0.02 * math.cos(2.0 * math.pi * i / cycle) for i in range(steps)]

    bars_a = _generate_bars_from_returns(ret_a, 100.0, "AAA")
    bars_b = _generate_bars_from_returns(ret_b, 100.0, "BBB")

    scanner = CorrelationScanner()
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="AAA", symbol_b="BBB", timeframe="60", window_horizon="24h")

    assert abs(res.pearson) < 0.05
    assert abs(res.spearman) < 0.05
    assert res.classification == CorrelationClassification.NEUTRAL


def test_changing_correlation_regime_and_breakdown():
    """
    Scenario 4: Changing correlation across time (regime shift and breakdown detection).
    First half positive (+1.0), second half negative (-1.0).
    """
    half = 40
    ret_first = [0.015 * math.sin(i / 3.0) for i in range(half)]
    ret_second = [0.015 * math.sin(i / 3.0) for i in range(half)]

    ret_a = ret_first + ret_second
    # B matches A in first half, then inverts in second half
    ret_b = ret_first + [-1.0 * r for r in ret_second]

    bars_a = _generate_bars_from_returns(ret_a, 100.0, "ASSET_A")
    bars_b = _generate_bars_from_returns(ret_b, 100.0, "ASSET_B")

    scanner = CorrelationScanner()
    res = scanner.analyze_pair(
        bars_a,
        bars_b,
        symbol_a="ASSET_A",
        symbol_b="ASSET_B",
        timeframe="60",
        window_horizon=20,  # 20 bars rolling
    )

    # Rolling correlation should show high positive at start and negative at end
    assert len(res.rolling_correlation) > 0
    assert res.rolling_correlation[0].pearson > 0.90
    assert res.rolling_correlation[-1].pearson < -0.90
    # Stability standard deviation should be large (> 0.50)
    assert res.correlation_stability > 0.50
    # Breakdown and regime shift must be flagged
    assert res.regime_analysis.breakdown_detected is True
    assert res.regime_analysis.regime_shift_detected is True


def test_noisy_relationships_degradation():
    """
    Scenario 5: Noisy relationship: Pearson correlation degrades monotonically with added noise.
    """
    np.random.seed(42)
    n = 120
    signal = np.random.normal(0, 0.01, n)
    low_noise = signal + np.random.normal(0, 0.003, n)
    high_noise = signal + np.random.normal(0, 0.03, n)

    r_low = pearson_correlation(signal, low_noise)
    r_high = pearson_correlation(signal, high_noise)

    assert r_low > 0.85
    assert r_high < r_low
    assert r_high < 0.60


def test_missing_observations_and_alignment_handling():
    """
    Scenario 6: Missing observations & timestamp alignment gaps.
    """
    # Asset A has bars 0 to 100
    bars_a = [
        {"timestamp": i * 3600, "close": 100.0 + i * 0.1, "symbol": "A", "resolution": "60"}
        for i in range(100)
    ]
    # Asset B only has even timestamps, plus a 10-hour gap at hour 50
    bars_b = []
    for i in range(0, 100, 2):
        if 40 <= i <= 50:
            continue  # gap
        bars_b.append({"timestamp": i * 3600, "close": 50.0 + i * 0.05, "symbol": "B", "resolution": "60"})

    scanner = CorrelationScanner()
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="A", symbol_b="B", timeframe="60", window_horizon="24h")

    # Matched count should match the count of bars_b
    assert res.observation_count == len(bars_b) - 1
    assert res.data_quality.missing_bars_b > 0
    assert any("Gaps detected" in note for note in res.data_quality.quality_notes)


def test_duplicate_candle_handling():
    """
    Scenario 7: Duplicate candle detection & deduplication.
    """
    bars_a = [
        {"timestamp": 1000, "close": 100.0, "symbol": "A", "resolution": "60"},
        {"timestamp": 1000, "close": 101.0, "symbol": "A", "resolution": "60"},  # duplicate
        {"timestamp": 2000, "close": 102.0, "symbol": "A", "resolution": "60"},
        {"timestamp": 3000, "close": 103.0, "symbol": "A", "resolution": "60"},
        {"timestamp": 4000, "close": 104.0, "symbol": "A", "resolution": "60"},
    ]
    bars_b = [
        {"timestamp": 1000, "close": 50.0, "symbol": "B", "resolution": "60"},
        {"timestamp": 2000, "close": 51.0, "symbol": "B", "resolution": "60"},
        {"timestamp": 3000, "close": 52.0, "symbol": "B", "resolution": "60"},
        {"timestamp": 4000, "close": 53.0, "symbol": "B", "resolution": "60"},
    ]

    scanner = CorrelationScanner(min_observations=3)
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="A", symbol_b="B", timeframe="60", window_horizon=3)

    assert res.data_quality.duplicate_timestamps_dropped == 1
    assert any("Deduplicated" in note for note in res.data_quality.quality_notes)


def test_constant_stale_data_zero_variance():
    """
    Scenario 8: Constant prices (zero variance) gracefully return 0.0 correlation.
    """
    bars_a = [{"timestamp": i * 3600, "close": 100.0, "symbol": "A", "resolution": "60"} for i in range(30)]
    bars_b = [{"timestamp": i * 3600, "close": 50.0 + i * 0.1, "symbol": "B", "resolution": "60"} for i in range(30)]

    scanner = CorrelationScanner()
    res = scanner.analyze_pair(bars_a, bars_b, symbol_a="A", symbol_b="B", timeframe="60")

    assert res.pearson == 0.0
    assert res.spearman == 0.0
    assert res.data_quality.zero_variance_detected is True
    assert res.classification == CorrelationClassification.NEUTRAL


def test_correlation_matrix_generation():
    """
    Scenario 9: Multi-asset correlation matrix generation.
    """
    returns_base = [0.01 * math.sin(i / 2.0) for i in range(50)]
    bars = {
        "BTC": _generate_bars_from_returns(returns_base, 100.0, "BTC"),
        "ETH": _generate_bars_from_returns([1.5 * r for r in returns_base], 100.0, "ETH"),  # correlated
        "INV": _generate_bars_from_returns([-1.0 * r for r in returns_base], 100.0, "INV"),  # inverse
    }

    matrix_res = compute_correlation_matrix(bars, timeframe="60")

    assert matrix_res.symbols == ["BTC", "ETH", "INV"]
    mat = matrix_res.pearson_matrix
    # Diagonals are 1.0
    assert mat[0][0] == 1.0
    assert mat[1][1] == 1.0
    assert mat[2][2] == 1.0
    # BTC & ETH ~ +1.0
    assert pytest.approx(mat[0][1], abs=1e-4) == 1.0
    assert mat[1][0] == mat[0][1]
    # BTC & INV ~ -1.0
    assert pytest.approx(mat[0][2], abs=1e-4) == -1.0
    assert mat[2][0] == mat[0][2]


def test_horizon_to_observation_bars():
    """
    Scenario 10: Horizon conversions across timeframes.
    """
    assert horizon_to_observation_bars("24h", "60") == 24
    assert horizon_to_observation_bars("24h", "15") == 96
    assert horizon_to_observation_bars("24h", "1") == 1440
    assert horizon_to_observation_bars("3d", "60") == 72
    assert horizon_to_observation_bars("7d", "60") == 168
    assert horizon_to_observation_bars("14d", "60") == 336
    assert horizon_to_observation_bars("30d", "60") == 720
    assert horizon_to_observation_bars("30d", "D") == 30
    assert horizon_to_observation_bars(50, "60") == 50

