from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_hyperliquid_research import run_validation, _assert_report_ok


@pytest.mark.integration
def test_hyperliquid_arb_100_bars_all_strategies(tmp_path: Path, monkeypatch) -> None:
    """Export ARB 1m+5m from Hyperliquid, optimize every strategy, compare (walk-forward)."""
    db_path = tmp_path / "validate.db"
    out_dir = tmp_path / "ohlc"
    log_path = tmp_path / "validate.log"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))

    import logging

    from scripts.validate_hyperliquid_research import _configure_logging

    _configure_logging(log_path, verbose=False)

    try:
        report = run_validation(
            src="arb",
            dst="usdt",
            intervals=["1", "5"],
            max_bars=100,
            output_dir=out_dir,
            database_path=db_path,
            train_fraction=0.65,
        )
    except Exception as exc:
        pytest.skip(f"hyperliquid unavailable or export failed: {exc}")

    _assert_report_ok(report)
    assert (out_dir / "ARBUSDT_1.csv").is_file()
    assert (out_dir / "ARBUSDT_5.csv").is_file()

    from lab.store.database import init_database, open_database
    from lab.store.queries import fetch_best_sweep
    from traderbot.algorithms.registry import backtest_strategy_ids

    connection = open_database(db_path)
    init_database(connection)
    try:
        for interval in ("1", "5"):
            for strategy_id in backtest_strategy_ids():
                row = fetch_best_sweep(
                    connection,
                    strategy_id=strategy_id,
                    symbol="ARBUSDT",
                    resolution=interval,
                )
                assert row is not None, f"missing sweep for {strategy_id} ARBUSDT {interval}"
                assert row.get("best_params")
    finally:
        connection.close()

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
