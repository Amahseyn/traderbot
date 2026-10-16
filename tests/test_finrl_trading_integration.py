from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.finrl_ema_intraday import FinrlEmaIntradayAlgorithm
from traderbot.integrations.finrl_trading.paths import finrl_trading_root, traderbot_root


def test_finrl_trading_root_sibling():
    root = finrl_trading_root()
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
    from scripts.validate_finrl_platform import assert_signals_no_lookahead

    result = assert_signals_no_lookahead("finrl_ema_intraday", bar_count=300)
    assert result["lookahead"] == "pass"
