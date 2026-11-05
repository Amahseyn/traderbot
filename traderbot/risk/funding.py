from __future__ import annotations

import math
from typing import Any, Literal

from traderbot.risk.pair_models import FundingRiskEstimate

HOURS_PER_YEAR = 365.0 * 24.0  # 8760 hours
MAX_PLAUSIBLE_HOURLY_FUNDING_RATE = 0.05  # 5% per hour is far above any legitimate rate


def calculate_funding_payment(
    quantity: float,
    mark_price: float,
    side: Literal["LONG", "BUY", "SHORT", "SELL"] | str,
    funding_rate: float,
    *,
    max_plausible_rate: float = MAX_PLAUSIBLE_HOURLY_FUNDING_RATE,
) -> float:
    """
    Calculate signed funding payment for a linear perpetual futures position.

    Notional: |quantity| * mark_price
    Payment: direction * notional * funding_rate
      - Positive payment (+): Outflow from account (position pays funding).
      - Negative payment (-): Inflow to account (position receives funding).

    Side convention:
      - LONG / BUY: d = +1 (pays when rate > 0, receives when rate < 0)
      - SHORT / SELL: d = -1 (receives when rate > 0, pays when rate < 0)
    """
    if not math.isfinite(mark_price) or mark_price <= 0:
        raise ValueError(f"mark price must be positive and finite, got {mark_price}")
    if not math.isfinite(funding_rate):
        raise ValueError(f"funding rate must be finite, got {funding_rate}")
    if abs(funding_rate) > max_plausible_rate:
        raise ValueError(
            f"funding rate {funding_rate} exceeds plausibility threshold {max_plausible_rate}; "
            "verify whether a percentage value was passed without dividing by 100"
        )
    if not math.isfinite(quantity) or quantity == 0:
        return 0.0

    side_normalized = str(side).strip().upper()
    if side_normalized in ("LONG", "BUY"):
        direction = 1.0
    elif side_normalized in ("SHORT", "SELL"):
        direction = -1.0
    else:
        raise ValueError(f"unsupported side: {side!r}; expected LONG, BUY, SHORT, or SELL")

    notional = abs(quantity) * mark_price
    return direction * notional * funding_rate


def calculate_annualized_funding_apr(
    rate: float,
    funding_interval_hours: int = 1,
) -> float:
    """
    Compute simple annualized funding percentage: rate * periods_per_year * 100.
    For Hyperliquid (1h interval): 8760 periods/year.
    """
    if funding_interval_hours <= 0:
        raise ValueError("funding_interval_hours must be positive")
    periods_per_year = HOURS_PER_YEAR / funding_interval_hours
    return rate * periods_per_year * 100.0


def evaluate_pair_funding_risk(
    *,
    symbol_a: str,
    symbol_b: str,
    leg_a_qty: float,
    leg_b_qty: float,
    mark_a: float,
    mark_b: float,
    funding_rate_a: float,
    funding_rate_b: float,
    funding_interval_hours: int = 1,
    max_adverse_apr: float = 0.25,
) -> FundingRiskEstimate:
    """
    Evaluate combined funding cash flow and carry drag for a two-leg perpetual pair.
    """
    side_a = "LONG" if leg_a_qty >= 0 else "SHORT"
    side_b = "LONG" if leg_b_qty >= 0 else "SHORT"

    payment_a = calculate_funding_payment(leg_a_qty, mark_a, side_a, funding_rate_a)
    payment_b = calculate_funding_payment(leg_b_qty, mark_b, side_b, funding_rate_b)

    net_payment = payment_a + payment_b
    total_notional = (abs(leg_a_qty) * mark_a) + (abs(leg_b_qty) * mark_b)

    if total_notional > 0:
        periods_per_year = HOURS_PER_YEAR / funding_interval_hours
        net_annualized_apr = (net_payment / total_notional) * periods_per_year * 100.0
    else:
        net_annualized_apr = 0.0

    # Breach condition: Net payment is an outflow (positive net payment) and exceeds ceiling
    adverse_carry_breach = bool(
        net_payment > 0 and net_annualized_apr > (max_adverse_apr * 100.0)
    )

    if adverse_carry_breach:
        status = "ADVERSE_FUNDING_BREACH"
    elif net_payment > 0:
        status = "FUNDING_OUTFLOW_ACCEPTABLE"
    elif net_payment < 0:
        status = "FUNDING_INFLOW_INCOME"
    else:
        status = "FUNDING_NEUTRAL"

    return FundingRiskEstimate(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        hourly_rate_a=funding_rate_a,
        hourly_rate_b=funding_rate_b,
        payment_a_hourly=payment_a,
        payment_b_hourly=payment_b,
        net_payment_hourly=net_payment,
        net_annualized_apr=net_annualized_apr,
        status=status,
        adverse_carry_breach=adverse_carry_breach,
    )


def analyze_funding_rate_trend(
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyze historical funding prints to verify dynamic rate behavior rather than assuming constancy.
    Detects rate variance, sign flips, and adverse trend shifts.
    """
    if not history:
        return {
            "observations": 0,
            "mean_rate": 0.0,
            "std_rate": 0.0,
            "has_flipped_sign": False,
            "latest_rate": 0.0,
        }

    rates = [float(row.get("funding_rate", 0.0)) for row in history]
    n = len(rates)
    mean_rate = sum(rates) / n
    variance = sum((r - mean_rate) ** 2 for r in rates) / n if n > 1 else 0.0
    std_rate = math.sqrt(variance)

    has_positive = any(r > 0 for r in rates)
    has_negative = any(r < 0 for r in rates)
    has_flipped_sign = bool(has_positive and has_negative)

    return {
        "observations": n,
        "mean_rate": mean_rate,
        "std_rate": std_rate,
        "has_flipped_sign": has_flipped_sign,
        "latest_rate": rates[-1],
    }

