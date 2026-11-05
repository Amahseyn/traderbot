from __future__ import annotations

import math
import pytest

from traderbot.risk.funding import (
    calculate_funding_payment,
    calculate_annualized_funding_apr,
    evaluate_pair_funding_risk,
    analyze_funding_rate_trend,
)
from traderbot.risk.pair_models import FundingRiskEstimate


def test_calculate_funding_payment_long_and_short():
    # 10 BTC Long @ 50,000 USD mark price with +0.0001 (0.01%) 1h rate
    # Notional = 500,000. Long pays positive funding: 500,000 * 0.0001 = 50.0
    payment_long = calculate_funding_payment(
        quantity=10.0,
        mark_price=50_000.0,
        side="LONG",
        funding_rate=0.0001,
    )
    assert math.isclose(payment_long, 50.0, rel_tol=1e-6)

    # 10 BTC Short @ 50,000 USD mark price with +0.0001 (0.01%) 1h rate
    # Short receives funding: -50.0
    payment_short = calculate_funding_payment(
        quantity=10.0,
        mark_price=50_000.0,
        side="SHORT",
        funding_rate=0.0001,
    )
    assert math.isclose(payment_short, -50.0, rel_tol=1e-6)


def test_calculate_annualized_funding_apr():
    # 1h interval has 8760 periods/year.
    # Rate = 0.0001 -> APR = 0.0001 * 8760 * 100% = 87.6%
    apr_1h = calculate_annualized_funding_apr(rate=0.0001, funding_interval_hours=1)
    assert math.isclose(apr_1h, 87.6, rel_tol=1e-4)

    # 8h interval has 1095 periods/year.
    # Rate = 0.0001 -> APR = 0.0001 * 1095 * 100% = 10.95%
    apr_8h = calculate_annualized_funding_apr(rate=0.0001, funding_interval_hours=8)
    assert math.isclose(apr_8h, 10.95, rel_tol=1e-4)


def test_evaluate_pair_funding_risk_offsetting_rates():
    # Leg A: Long 1.0 BTC @ 60,000, rate = +0.00005 (+0.005%/h)
    # Payment A = +1 * 60,000 * 0.00005 = +3.0 USD/h (paying)
    # Leg B: Short 20.0 ETH @ 3,000, rate = +0.00005 (+0.005%/h)
    # Payment B = -1 * 60,000 * 0.00005 = -3.0 USD/h (receiving)
    # Net payment = 0.0 USD/h -> Net APR = 0.0%
    result = evaluate_pair_funding_risk(
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=1.0,
        leg_b_qty=-20.0,
        mark_a=60_000.0,
        mark_b=3_000.0,
        funding_rate_a=0.00005,
        funding_rate_b=0.00005,
        funding_interval_hours=1,
        max_adverse_apr=0.25,
    )
    assert isinstance(result, FundingRiskEstimate)
    assert math.isclose(result.payment_a_hourly, 3.0, rel_tol=1e-5)
    assert math.isclose(result.payment_b_hourly, -3.0, rel_tol=1e-5)
    assert math.isclose(result.net_payment_hourly, 0.0, abs_tol=1e-6)
    assert math.isclose(result.net_annualized_apr, 0.0, abs_tol=1e-4)
    assert not result.adverse_carry_breach
    assert result.status == "FUNDING_NEUTRAL"


def test_evaluate_pair_funding_risk_compounding_drag_breach():
    # Long Leg A under positive rate (+0.0001) -> paying +6.0 USD/h
    # Short Leg B under negative rate (-0.0001) -> paying +6.0 USD/h (shorts pay under negative rate!)
    # Both legs are bleeding carry! Net payment = +12.0 USD/h
    # Total notional = 120,000 USD
    # Net APR = (12.0 / 120,000) * 8760 * 100% = 87.6% APR!
    # With max_adverse_apr=0.25 (25%), this must trigger adverse_carry_breach
    result = evaluate_pair_funding_risk(
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=1.0,
        leg_b_qty=-20.0,
        mark_a=60_000.0,
        mark_b=3_000.0,
        funding_rate_a=0.0001,
        funding_rate_b=-0.0001,
        funding_interval_hours=1,
        max_adverse_apr=0.25,
    )
    assert result.adverse_carry_breach is True
    assert math.isclose(result.net_payment_hourly, 12.0, rel_tol=1e-5)
    assert math.isclose(result.net_annualized_apr, 87.6, rel_tol=1e-4)
    assert result.status == "ADVERSE_FUNDING_BREACH"


def test_evaluate_pair_funding_input_validation():
    # Invalid mark price
    with pytest.raises(ValueError, match="mark price must be positive"):
        calculate_funding_payment(quantity=1.0, mark_price=0.0, side="LONG", funding_rate=0.0001)

    # NaN funding rate
    with pytest.raises(ValueError, match="funding rate must be finite"):
        calculate_funding_payment(quantity=1.0, mark_price=100.0, side="LONG", funding_rate=float("nan"))

    # Plausibility threshold breach (rate = 0.10 means 10% per hour!)
    with pytest.raises(ValueError, match="exceeds plausibility threshold"):
        calculate_funding_payment(quantity=1.0, mark_price=100.0, side="LONG", funding_rate=0.10)


def test_analyze_funding_rate_trend():
    # Simulate funding history where funding was positive (+0.0001) then flipped negative (-0.0002)
    history = [
        {"funding_rate": 0.0001, "time_unix_seconds": 1000 + i * 3600} for i in range(10)
    ] + [
        {"funding_rate": -0.0002, "time_unix_seconds": 1000 + (10 + i) * 3600} for i in range(10)
    ]
    trend = analyze_funding_rate_trend(history)
    assert trend["observations"] == 20
    assert trend["has_flipped_sign"] is True
    assert trend["latest_rate"] == -0.0002
    assert trend["mean_rate"] < 0.0

