"""
FinRL-Trading feature map for traderbot (what runs where).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Intraday / Hyperliquid: backtest + live via traderbot Algorithm registry
FINRL_HYPERLIQUID_STRATEGY_IDS: tuple[str, ...] = (
    "finrl_ema_intraday",
    "ensemble",
    "online_logistic",
    "ema_cross",
    "scalp_dip",
    "rsi_trend",
    "macd_cross",
    "breakout_atr",
)

# Ensemble presets aligned with FinRL / docs/ensemble-and-1m.md
FINRL_ENSEMBLE_PRESETS: tuple[str, ...] = (
    "1m_scalp_trend",
    "1m_pattern_ma",
    "1m_ml_trend",
    "intraday_trend_stack",
)

# Subprocess / pipeline runners in FinRL-Trading repo
FINRL_EQUITY_RUNNERS: tuple[str, ...] = (
    "adaptive_rotation_backtest",
    "adaptive_rotation_100period_report",
    "hyperliquid_intraday_experiment",
    "ml_stock_selection",
    "fundamental_portfolio_drl",
)

# Future perp RL training is external; traderbot provides PerpRlEnv + FrozenPolicySpec.
TRADERBOT_PERP_RL_MODULES: tuple[str, ...] = (
    "traderbot.backtesting.perp_rl_env",
    "traderbot.integrations.finrl_trading.policy_serve",
)


@dataclass(frozen=True, slots=True)
class FinrlCapability:
    id: str
    title: str
    finrl_module: str
    traderbot_surface: str
    hyperliquid: bool
    nobitex: bool


FINRL_CAPABILITIES: tuple[FinrlCapability, ...] = (
    FinrlCapability(
        id="hyperliquid_intraday_ema",
        title="Hyperliquid 1m/5m EMA (FinRL preset)",
        finrl_module="src/backtest/intraday_engine.py",
        traderbot_surface="strategy:finrl_ema_intraday + pipeline:finrl-platform",
        hyperliquid=True,
        nobitex=False,
    ),
    FinrlCapability(
        id="adaptive_rotation",
        title="Adaptive multi-asset rotation (US equity)",
        finrl_module="src/strategies/run_adaptive_rotation_strategy.py",
        traderbot_surface="pipeline:finrl-platform step 4 / finrl run",
        hyperliquid=False,
        nobitex=False,
    ),
    FinrlCapability(
        id="ml_stock_selection",
        title="ML fundamental stock selection",
        finrl_module="src/strategies/ml_strategy.py",
        traderbot_surface="subprocess / FinRL notebook (equity data)",
        hyperliquid=False,
        nobitex=False,
    ),
    FinrlCapability(
        id="ensemble_intraday",
        title="Ensemble intraday stacks",
        finrl_module="docs/ensemble-and-1m.md",
        traderbot_surface="strategy:ensemble + compare in finrl-platform",
        hyperliquid=True,
        nobitex=True,
    ),
    FinrlCapability(
        id="drl_portfolio",
        title="DRL portfolio allocator",
        finrl_module="src/strategies/fundamental_portfolio_drl.py",
        traderbot_surface="FinRL backtest engine (equity)",
        hyperliquid=False,
        nobitex=False,
    ),
)


def capabilities_api_payload() -> dict[str, Any]:
    return {
        "hyperliquid_strategy_ids": list(FINRL_HYPERLIQUID_STRATEGY_IDS),
        "ensemble_presets": list(FINRL_ENSEMBLE_PRESETS),
        "equity_runners": list(FINRL_EQUITY_RUNNERS),
        "capabilities": [
            {
                "id": c.id,
                "title": c.title,
                "finrl_module": c.finrl_module,
                "traderbot_surface": c.traderbot_surface,
                "hyperliquid": c.hyperliquid,
                "nobitex": c.nobitex,
            }
            for c in FINRL_CAPABILITIES
        ],
    }
