from __future__ import annotations

import pytest

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.finrl_ema_intraday import FinrlEmaIntradayAlgorithm
from traderbot.integrations.finrl_trading.paths import finrl_trading_root, traderbot_root


def _finrl_trading_root_or_skip():
    try:
        return finrl_trading_root()
    except FileNotFoundError:
        pytest.skip("FinRL-Trading not cloned (set FINRL_TRADING_ROOT or clone sibling repo)")


def test_finrl_trading_root_sibling_optional():
    """The sibling FinRL-Trading checkout is optional; traderbot vendors the needed core."""
    root = _finrl_trading_root_or_skip()
    assert root.is_dir()
    assert (root / "src").is_dir()


def test_traderbot_root():
    assert (traderbot_root() / "pyproject.toml").is_file()


def test_finrl_ema_intraday_algorithm():
    algo = algorithm_for_id("finrl_ema_intraday", fast=12, slow=48)
    assert isinstance(algo, FinrlEmaIntradayAlgorithm)


def test_load_shared_env_no_crash():
    from traderbot.integrations.finrl_trading.env import load_shared_env

    files = load_shared_env()
    assert isinstance(files, list)


def test_finrl_ema_intraday_no_lookahead():
    import importlib.util

    script = traderbot_root() / "scripts" / "validate_finrl_platform.py"
    spec = importlib.util.spec_from_file_location("validate_finrl_platform", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    result = module.assert_signals_no_lookahead("finrl_ema_intraday", bar_count=300)
    assert result["lookahead"] == "pass"


def test_finrl_ema_level_lag_default():
    algo = algorithm_for_id("finrl_ema_intraday", fast=12, slow=48)
    assert algo.signal_style == "level_lag"


def test_finrl_static_leakage_checks():
    from traderbot.integrations.finrl_trading.leakage_checks import run_finrl_static_leakage_checks

    steps = run_finrl_static_leakage_checks()
    assert steps
    assert steps[0].get("finrl_ema_shift") == "pass"
    assert any(
        step.get("finrl_min_variance_as_of") in ("pass", "skipped") for step in steps
    )


def test_frozen_policy_spec_fallback():
    from traderbot.integrations.finrl_trading.policy_serve import FrozenPolicySpec, load_algorithm_from_policy

    spec = FrozenPolicySpec(strategy_id="finrl_ema_intraday", kwargs={"fast": 12, "slow": 48})
    algo = load_algorithm_from_policy(spec)
    assert algo.name == "finrl_ema_intraday"
