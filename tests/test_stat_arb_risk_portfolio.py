from __future__ import annotations

import math
import numpy as np
import pytest

from traderbot.risk.pair_models import PairRiskState, StatArbRiskVerdict
from traderbot.risk.portfolio import PortfolioRiskLimits, PortfolioRiskManager


def test_portfolio_shared_symbols_and_concentration():
    limits = PortfolioRiskLimits(
        max_concurrent_pairs=5,
        max_shared_symbol_pairs=2,
        max_symbol_concentration_pct=0.30,  # Max 30% of equity on any single symbol
    )
    pm = PortfolioRiskManager(limits)
    pm.reset_session(100_000.0)

    # Pair 1: Long BTC (10k), Short ETH (10k)
    pair1 = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.2,
        leg_b_qty=-3.333,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
        allocated_capital=20_000.0,
    )
    pm.register_pair(pair1)

    # Pair 2: Long BTC (10k), Short SOL (10k)
    pair2 = PairRiskState(
        pair_id="BTC-SOL",
        symbol_a="BTC",
        symbol_b="SOL",
        leg_a_qty=0.2,
        leg_b_qty=-66.66,
        current_price_a=50_000.0,
        current_price_b=150.0,
        allocated_capital=20_000.0,
    )
    pm.register_pair(pair2)

    # Both pairs share BTC!
    shared = pm.get_shared_symbols()
    assert "BTC" in shared
    assert set(shared["BTC"]) == {"BTC-ETH", "BTC-SOL"}
    assert pm.get_symbol_gross_exposure("BTC") == 20_000.0
    assert pm.get_symbol_net_exposure("BTC") == 20_000.0

    # Pair 3 tries to also use BTC (Long BTC 15k, Short AVAX 15k)
    # This breaches max_shared_symbol_pairs=2!
    verdict3 = pm.evaluate_pair_entry(
        pair_id="BTC-AVAX",
        symbol_a="BTC",
        symbol_b="AVAX",
        notional_a=15_000.0,
        notional_b=15_000.0,
        total_equity=100_000.0,
    )
    assert verdict3.allowed is False
    assert "max_shared_symbol_pairs_reached" in verdict3.reason


def test_portfolio_margin_and_two_legs_not_risk_free():
    # Demonstrating the core principle: Two legs are NOT independent risk-free positions!
    # Gross notional is charged against maintenance margin.
    limits = PortfolioRiskLimits(
        max_symbol_concentration_pct=1.0,  # allow up to 10k per symbol
        max_gross_exposure_equity=5.0,     # allow up to 50k gross
        maintenance_margin_pct=0.05,       # 5% maintenance margin
        min_available_margin_pct=0.95,     # require 9,500 buffer on 10,000 equity
    )
    pm = PortfolioRiskManager(limits)
    pm.reset_session(10_000.0)  # 10,000 USD equity

    # Propose pair trade with 9,000 USD Leg A and 9,000 USD Leg B
    # Total Gross Notional = 18,000 USD
    # Required Margin = 18,000 * 0.05 = 900 USD
    # Available Margin = 10,000 - 900 = 9,100 USD < 9,500 USD buffer required!
    verdict = pm.evaluate_pair_entry(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        notional_a=9_000.0,
        notional_b=9_000.0,
        total_equity=10_000.0,
    )
    assert verdict.allowed is False
    assert "insufficient_available_margin" in verdict.reason


def test_portfolio_aggregate_long_and_short_exposure():
    pm = PortfolioRiskManager(PortfolioRiskLimits())
    pm.reset_session(100_000.0)

    # Pair 1: Long BTC (20k), Short ETH (20k)
    pair1 = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.4,
        leg_b_qty=-20.0 / 3.0,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
    )
    pm.register_pair(pair1)

    # Pair 2: Long SOL (15k), Short BTC (10k)
    pair2 = PairRiskState(
        pair_id="SOL-BTC",
        symbol_a="SOL",
        symbol_b="BTC",
        leg_a_qty=100.0,
        leg_b_qty=-0.2,
        current_price_a=150.0,
        current_price_b=50_000.0,
    )
    pm.register_pair(pair2)

    # BTC net exposure: +20k (Pair 1) - 10k (Pair 2) = +10k Long
    # ETH net exposure: -20k Short
    # SOL net exposure: +15k Long
    # Aggregate Long = 10k (BTC) + 15k (SOL) = 25,000
    # Aggregate Short = 20k (ETH) = 20,000
    # Portfolio Gross = 20k + 20k + 15k + 10k = 65,000
    # Portfolio Net = +25,000 - 20,000 = +5,000
    assert math.isclose(pm.get_symbol_net_exposure("BTC"), 10_000.0, rel_tol=1e-5)
    assert math.isclose(pm.get_aggregate_long_exposure(), 25_000.0, rel_tol=1e-5)
    assert math.isclose(pm.get_aggregate_short_exposure(), 20_000.0, rel_tol=1e-5)
    assert math.isclose(pm.get_portfolio_gross_notional(), 65_000.0, rel_tol=1e-5)
    assert math.isclose(pm.get_portfolio_net_notional(), 5_000.0, rel_tol=1e-5)


def test_portfolio_correlated_spread_exposure_rejection():
    # Test Correlation-Aware Exposure:
    # If Pair 1 spread and Pair 2 spread have r > 0.70, entering Pair 2 is rejected!
    limits = PortfolioRiskLimits(max_spread_correlation=0.70)
    pm = PortfolioRiskManager(limits)
    pm.reset_session(100_000.0)

    # Generate synthetic spread 1
    np.random.seed(42)
    spread1 = list(np.cumsum(np.random.normal(0, 0.05, 50)))
    pair1 = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.1,
        leg_b_qty=-1.6,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
    )
    pm.register_pair(pair1, spread_history=spread1)

    # Spread 2 is 95% correlated with Spread 1
    spread2 = [s * 0.95 + np.random.normal(0, 0.005) for s in spread1]

    verdict = pm.evaluate_pair_entry(
        pair_id="BTC-SOL",
        symbol_a="BTC",
        symbol_b="SOL",
        notional_a=5_000.0,
        notional_b=5_000.0,
        total_equity=100_000.0,
        spread_history=spread2,
    )
    assert verdict.allowed is False
    assert "excessive_spread_correlation" in verdict.reason
