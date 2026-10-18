from __future__ import annotations

import sys
from pathlib import Path

import pytest

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.finrl_ema_intraday import FinrlEmaIntradayAlgorithm
from traderbot.integrations.finrl_trading.paths import finrl_trading_root, traderbot_root

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _finrl_trading_root_or_skip():
    try:
        return finrl_trading_root()
    except FileNotFoundError:
        pytest.skip("FinRL-Trading not cloned (set FINRL_TRADING_ROOT or clone sibling repo)")


def test_finrl_trading_root_sibling():
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
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.validate_finrl_platform import assert_signals_no_lookahead

    result = assert_signals_no_lookahead("finrl_ema_intraday", bar_count=300)
    assert result["lookahead"] == "pass"
