from pathlib import Path

import pytest

from traderbot.backtesting.live_tune import (
    default_live_tune_param_grid,
    fetch_live_tune_bars,
    run_live_tune_sweep,
)
from traderbot.backtesting.sweep import SweepOptions, run_strategy_sweep
from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.terminal.paper_portfolio import default_paper_initial_cash


def test_default_live_tune_param_grid_sma():
    grid = default_live_tune_param_grid("sma_cross")
    assert set(grid) == {"fast", "slow"}


def test_fetch_live_tune_bars_empty(monkeypatch):
    monkeypatch.setattr(
        "traderbot.backtesting.live_tune.fetch_recent_closed_bars",
        lambda **_kwargs: [],
    )
    with pytest.raises(ValueError, match="No closed bars from Nobitex"):
        fetch_live_tune_bars("ZAMAIRT", "1", 100)


def test_run_live_tune_uses_api_bars(monkeypatch):
    bars = [
        {
            "symbol": "ZAMAIRT",
            "resolution": "1",
            "timestamp": index,
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.0 + index,
            "volume": 1.0,
        }
        for index in range(80)
    ]
    monkeypatch.setattr(
        "traderbot.backtesting.live_tune.fetch_recent_closed_bars",
        lambda **_kwargs: bars,
    )
    payload = run_live_tune_sweep(
        strategy_id="sma_cross",
        symbol="ZAMAIRT",
        interval="1",
        dst="rls",
        max_bars=80,
        holdout_tail_bars=20,
    )
    assert payload["best_params"]
    assert payload["live_tune"]["data_source"] == "nobitex_api"
    assert payload["bars"] == 80


def test_sweep_max_bars_trims_tail(tmp_path):
    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with csv_path.open("a", encoding="utf-8") as handle:
        for index in range(200):
            close = 100.0 + index
            handle.write(f"{index},{close},{close},{close},{close},1.0\n")
    payload = run_strategy_sweep(
        SweepOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [2, 5], "slow": [10, 20]},
            csv_path=csv_path,
            max_bars=100,
            holdout_tail_bars=20,
        ),
        default_strategy_namespace(),
    )
    assert payload["bars"] == 100


@pytest.mark.integration
def test_run_live_tune_on_repo_btcirt():
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "data" / "BTCIRT_60.csv"
    if not csv_path.is_file():
        pytest.skip("BTCIRT_60.csv not present")
    payload = run_live_tune_sweep(
        strategy_id="sma_cross",
        symbol="BTCIRT",
        interval="60",
        dst="rls",
    )
    assert payload["best_params"]
    assert payload["cash"] == default_paper_initial_cash("rls")
    assert payload["bars"] <= 100
