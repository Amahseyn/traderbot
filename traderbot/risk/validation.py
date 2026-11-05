from __future__ import annotations

from traderbot.risk.manager import RiskLimits
from traderbot.risk.pair_models import PairRiskLimits
from traderbot.risk.portfolio import PortfolioRiskLimits


def validate_pair_risk_limits(limits: PairRiskLimits) -> None:
    if limits.max_pair_allocation_pct <= 0 or limits.max_pair_allocation_pct > 1.0:
        raise ValueError("max_pair_allocation_pct must be in (0, 1.0]")
    if limits.max_gross_pair_exposure <= 0:
        raise ValueError("max_gross_pair_exposure must be positive")
    if limits.max_net_exposure_pct <= 0 or limits.max_net_exposure_pct > 1.0:
        raise ValueError("max_net_exposure_pct must be in (0, 1.0]")
    if limits.max_leverage < 1.0:
        raise ValueError("max_leverage must be >= 1.0")
    if limits.max_hedge_deviation_pct <= 0:
        raise ValueError("max_hedge_deviation_pct must be positive")
    if limits.max_holding_duration_bars < 1:
        raise ValueError("max_holding_duration_bars must be >= 1")
    if limits.max_pair_loss_pct <= 0:
        raise ValueError("max_pair_loss_pct must be positive")
    if limits.max_spread_divergence_z <= 0:
        raise ValueError("max_spread_divergence_z must be positive")
    if limits.max_adverse_funding_apr <= 0:
        raise ValueError("max_adverse_funding_apr must be positive")
    if limits.max_spread_vol_expansion <= 1.0:
        raise ValueError("max_spread_vol_expansion must be > 1.0")


def validate_portfolio_risk_limits(limits: PortfolioRiskLimits) -> None:
    if limits.max_aggregate_capital_cap <= 0:
        raise ValueError("max_aggregate_capital_cap must be positive")
    if limits.portfolio_daily_loss_limit_pct <= 0 or limits.portfolio_daily_loss_limit_pct > 100:
        raise ValueError("portfolio_daily_loss_limit_pct must be in (0, 100]")
    if limits.portfolio_max_drawdown_pct <= 0 or limits.portfolio_max_drawdown_pct > 100:
        raise ValueError("portfolio_max_drawdown_pct must be in (0, 100]")
    if limits.max_concurrent_positions < 1:
        raise ValueError("max_concurrent_positions must be >= 1")
    if limits.max_gross_exposure_equity <= 0:
        raise ValueError("max_gross_exposure_equity must be positive")
    if limits.max_concurrent_pairs < 1:
        raise ValueError("max_concurrent_pairs must be >= 1")
    if limits.max_portfolio_gross_notional <= 0:
        raise ValueError("max_portfolio_gross_notional must be positive")
    if limits.max_portfolio_net_notional_pct <= 0 or limits.max_portfolio_net_notional_pct > 1.0:
        raise ValueError("max_portfolio_net_notional_pct must be in (0, 1.0]")
    if limits.max_symbol_concentration_pct <= 0 or limits.max_symbol_concentration_pct > 1.0:
        raise ValueError("max_symbol_concentration_pct must be in (0, 1.0]")
    if limits.max_shared_symbol_pairs < 1:
        raise ValueError("max_shared_symbol_pairs must be >= 1")
    if limits.min_available_margin_pct <= 0 or limits.min_available_margin_pct >= 1.0:
        raise ValueError("min_available_margin_pct must be in (0, 1.0)")
    if not (-1.0 <= limits.max_spread_correlation <= 1.0):
        raise ValueError("max_spread_correlation must be in [-1.0, 1.0]")
    if limits.maintenance_margin_pct <= 0 or limits.maintenance_margin_pct >= 1.0:
        raise ValueError("maintenance_margin_pct must be in (0, 1.0)")


def validate_risk_limits(limits: RiskLimits) -> None:
    if limits.capital_cap <= 0:
        raise ValueError("capital_cap must be positive")
    if limits.daily_loss_limit_pct <= 0 or limits.daily_loss_limit_pct > 100:
        raise ValueError("daily_loss_limit_pct must be in (0, 100]")
    if limits.max_drawdown_pct <= 0 or limits.max_drawdown_pct > 100:
        raise ValueError("max_drawdown_pct must be in (0, 100]")
    if limits.volatility_target_pct <= 0:
        raise ValueError("volatility_target_pct must be positive")
    if limits.atr_lookback < 1:
        raise ValueError("atr_lookback must be >= 1")
    if limits.stop_loss_pct is not None:
        if limits.stop_loss_pct <= 0 or limits.stop_loss_pct >= 100:
            raise ValueError("stop_loss_pct must be in (0, 100) when set")
    if limits.pair_limits is not None:
        validate_pair_risk_limits(limits.pair_limits)
