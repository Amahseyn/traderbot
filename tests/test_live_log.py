from __future__ import annotations

import json

from lab.live_log import (
    assert_log_contains_strategy,
    parse_json_log_lines,
    summarize_live_job_log,
)
from lab.live_run_plan import build_live_run_combos


def test_parse_json_log_lines_skips_noise():
    log = "task: terminal-once\nnot json\n{\"event\": \"once\"}\n"
    rows = parse_json_log_lines(log)
    assert len(rows) == 1
    assert rows[0]["event"] == "once"


def test_summarize_live_job_log_once_signal_and_paper():
    log = "\n".join(
        [
            "task: terminal-once",
            json.dumps(
                {
                    "event": "once",
                    "strategy_id": "rsi_threshold",
                    "action": "buy",
                    "timestamp": 100,
                    "close": 1.25,
                    "mode": "paper",
                },
            ),
            json.dumps({"event": "paper_wallet", "initial_cash": 1000}),
            json.dumps(
                {
                    "event": "tick",
                    "status": "evaluated",
                    "strategy_id": "rsi_threshold",
                    "portfolio": {
                        "quote_cash": 500,
                        "quote_currency": "usdt",
                        "base_amount": 0.1,
                        "equity": 1000,
                        "mark_price": 1.25,
                    },
                },
            ),
        ],
    )
    summary = summarize_live_job_log(log)
    assert summary["strategy_ids"] == ["rsi_threshold"]
    assert summary["paper_initial_cash"] == 1000.0
    assert summary["paper_wallet"] is not None
    assert summary["paper_wallet"]["equity"] == 1000
    assert len(summary["markers"]) == 1
    assert summary["markers"][0]["action"] == "buy"


def test_summarize_live_terminal_banner_and_tune():
    log = "\n".join(
        [
            json.dumps(
                {
                    "terminal": "live",
                    "strategy": "sma_cross",
                    "interval": "60",
                    "symbol": "btc/usdt",
                },
            ),
            json.dumps(
                {
                    "event": "live_tune_sweep",
                    "strategy": "sma_cross",
                    "best_params": {"fast": 5},
                },
            ),
        ],
    )
    summary = summarize_live_job_log(log)
    assert summary["terminal_banner"]["strategy"] == "sma_cross"
    assert summary["live_tune_events"][0]["strategy"] == "sma_cross"
    assert summary["strategy_ids"] == ["sma_cross"]
    assert "optimize_result" in summary["phases"]


def test_summarize_live_tune_lifecycle_phases():
    log = "\n".join(
        [
            json.dumps({"event": "live_tune_start", "strategy": "sma_cross"}),
            json.dumps({"event": "live_tune_sweep", "strategy": "sma_cross", "status": "ok"}),
            json.dumps({"event": "live_tune_complete", "strategy": "sma_cross"}),
            json.dumps({"terminal": "once", "strategy": "sma_cross"}),
            json.dumps({"event": "once", "strategy_id": "sma_cross", "action": "hold"}),
        ],
    )
    summary = summarize_live_job_log(log)
    assert summary["live_tune_start_events"]
    assert summary["live_tune_complete_events"]
    assert "optimize" in summary["phases"]
    assert "optimize_done" in summary["phases"]
    assert "terminal_once" in summary["phases"]


def test_multi_strategy_logs_match_run_plan():
    combos = build_live_run_combos(
        multi_run=True,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[
            {"src": "btc", "dst": "usdt", "symbol": "BTCUSDT"},
        ],
        horizons=["5"],
        multi_strategy=True,
        strategy_id="sma_cross",
        batch_strategy_ids=["sma_cross", "rsi_threshold"],
    )
    logs: list[str] = []
    for combo in combos:
        logs.append(
            "\n".join(
                [
                    "task: terminal-once",
                    json.dumps(
                        {
                            "event": "once",
                            "strategy_id": combo.strategy_id,
                            "action": "hold",
                            "timestamp": 1,
                            "close": 1.0,
                        },
                    ),
                ],
            ),
        )
    found = [summarize_live_job_log(text)["strategy_ids"][0] for text in logs]
    assert found == ["sma_cross", "rsi_threshold"]
    for combo, log in zip(combos, logs, strict=True):
        assert_log_contains_strategy(log, combo.strategy_id)
