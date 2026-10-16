from __future__ import annotations

import pytest

from traderbot.integrations.wondertrader.paths import traderbot_root


def _wondertrader_root_or_skip():
    from traderbot.integrations.wondertrader.paths import wondertrader_root

    try:
        return wondertrader_root()
    except FileNotFoundError:
        pytest.skip("WonderTrader not cloned (see docs/wondertrader.md)")


def test_traderbot_root():
    assert (traderbot_root() / "pyproject.toml").is_file()


def test_wondertrader_root_sibling():
    root = _wondertrader_root_or_skip()
    assert (root / "dist" / "WtBtRunner" / "configbt.yaml").is_file()


def test_wondertrader_smoke():
    root = _wondertrader_root_or_skip()
    from traderbot.integrations.wondertrader.experiment import run_smoke_test

    result = run_smoke_test()
    assert result["ok"], result.get("output_tail", "")


def test_live_readiness_payload():
    _wondertrader_root_or_skip()
    from traderbot.integrations.wondertrader.live import assess_live_readiness

    payload = assess_live_readiness()
    assert payload["profiles"]
    assert payload["ready_for_paper_config"] is True


def test_capabilities_api():
    _wondertrader_root_or_skip()
    from traderbot.integrations.wondertrader import capabilities_api_payload

    cap = capabilities_api_payload()
    assert "backtest" in cap and "live" in cap


@pytest.mark.integration
def test_full_backtest_experiment():
    from traderbot.integrations.wondertrader.experiment import (
        native_runner_available,
        run_full_backtest_experiment,
    )

    _wondertrader_root_or_skip()
    if not native_runner_available():
        pytest.skip("WtBtRunner not built (macos_bt)")
    report = run_full_backtest_experiment(pnl_report=True)
    assert report["ok"], report
