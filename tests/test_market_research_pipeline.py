from __future__ import annotations

from traderbot.pipelines.market_research import (
    build_export_jobs,
    build_full_universe_research_body,
    build_single_market_research_body,
)


def test_build_single_market_export_jobs() -> None:
    body = build_single_market_research_body(
        market_symbol="ARBUSDT",
        intervals=["1", "5"],
        optimize_n_trials=40,
    )
    assert body["optimize_method"] == "optuna"
    assert body["optimize_n_trials"] == 40
    assert len(body["export_jobs"]) == 2
    assert body["export_jobs"][0]["symbol"] == "ARBUSDT"
    assert body["export_jobs"][0]["exchange"] == "hyperliquid"


def test_build_export_jobs_symbols() -> None:
    jobs = build_export_jobs(["BTCUSDT", "ETHUSDT"], intervals=["5"], export_days=14)
    assert len(jobs) == 2
    assert {job["symbol"] for job in jobs} == {"BTCUSDT", "ETHUSDT"}


def test_full_universe_body_lists_all_strategies(monkeypatch) -> None:
    monkeypatch.setattr(
        "traderbot.pipelines.market_research.resolve_market_symbols",
        lambda **_: ["BTCUSDT", "ETHUSDT"],
    )
    body = build_full_universe_research_body(intervals=["1", "5"], top_markets=2)
    assert body["max_export_combos"] == 4
    assert len(body["strategy_ids"]) >= 5
    assert len(body["export_jobs"]) == 4
