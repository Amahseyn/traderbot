from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from traderbot.discovery.universe import UniverseEntry
from traderbot.discovery.run import (
    DEFAULT_RESOLUTIONS,
    DiscoveryConfig,
    discovery_config_from_body,
    run_opportunity_discovery,
)


def _bars(count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    price = 50_000.0
    for index in range(count):
        price *= 1.0002
        rows.append(
            {
                "timestamp": 1_700_000_000 + index * 3600,
                "open": price,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 10.0,
            },
        )
    return rows


def test_run_opportunity_discovery_smoke(tmp_path: Path) -> None:
    def fake_universe(**_kwargs: object) -> list[UniverseEntry]:
        return [
            UniverseEntry(
                symbol_key="btc",
                market_symbol="BTCUSDT",
                mean_volume_quote_24h=1_000_000.0,
                bar_count_sample=24,
            ),
        ]

    def fake_bars(**_kwargs: object) -> list[dict[str, Any]]:
        return _bars(200)

    config = DiscoveryConfig(
        exchange="hyperliquid",
        symbols=["btc"],
        resolutions=["60"],
        strategy_ids=["sma_cross"],
        months=1,
        use_cache=False,
        min_trades=1,
        min_bars=100,
        min_oos_bars=20,
        max_symbols=1,
        out_dir=tmp_path,
    )
    report = run_opportunity_discovery(
        config,
        discover_universe=fake_universe,
        fetch_bars=fake_bars,
    )
    assert report["summary"]["candidates_evaluated"] == 1
    assert (tmp_path / "discovery_report.json").is_file()
    ranked = report.get("ranked") or []
    rejected = report.get("rejected") or []
    assert len(ranked) + len(rejected) == 1


def test_run_market_scan_without_strategies(tmp_path: Path) -> None:
    def fake_universe(**_kwargs: object) -> list[UniverseEntry]:
        return [
            UniverseEntry(
                symbol_key="btc",
                market_symbol="BTCUSDT",
                mean_volume_quote_24h=500_000.0,
                bar_count_sample=24,
            ),
        ]

    def fake_bars(**_kwargs: object) -> list[dict[str, Any]]:
        return _bars(150)

    config = DiscoveryConfig(
        exchange="hyperliquid",
        symbols=["btc"],
        resolutions=["60"],
        evaluate_strategies=False,
        min_bars=100,
        max_symbols=1,
        out_dir=tmp_path,
    )
    report = run_opportunity_discovery(
        config,
        discover_universe=fake_universe,
        fetch_bars=fake_bars,
    )
    assert report["config"]["evaluate_strategies"] is False
    assert report["config"]["scan_kind"] == "market_opportunity"
    assert report["summary"]["candidates_evaluated"] == 1
    ranked = report.get("ranked") or []
    if ranked:
        assert ranked[0].get("return_1bar_pct") is not None
        assert ranked[0].get("mean_quote_volume") is not None


def test_discovery_config_from_body_all_options(tmp_path: Path) -> None:
    body = {
        "exchange": "hyperliquid",
        "symbols": ["btc", "ETH"],
        "resolutions": ["5", "15", "60", "240", "D"],
        "strategy_ids": ["sma_cross", "rsi_threshold"],
        "months": 3,
        "use_cache": False,
        "cash": 25_000.0,
        "fee_role": "maker",
        "execution": "next_open",
        "min_trades": 3,
        "max_drawdown_pct": -25.0,
        "min_bars": 80,
        "min_oos_bars": 25,
        "min_mean_volume_quote": 50_000.0,
        "max_symbols": 12,
        "evaluate_strategies": True,
        "run_start_unix_seconds": 1_700_000_000,
        "run_end_unix_seconds": 1_800_000_000,
        "out": str(tmp_path / "artifact"),
        "scoring": {
            "weight_oos_return": 0.3,
            "require_oos_return": False,
            "sharpe_cap": 2.5,
        },
    }
    config = discovery_config_from_body(body)
    assert config.exchange == "hyperliquid"
    assert config.symbols == ["btc", "eth"]
    assert config.resolutions == list(DEFAULT_RESOLUTIONS)
    assert config.strategy_ids == ["sma_cross", "rsi_threshold"]
    assert config.months == 3
    assert config.use_cache is False
    assert config.cash == 25_000.0
    assert config.fee_role == "maker"
    assert config.execution == "next_open"
    assert config.min_trades == 3
    assert config.max_drawdown_pct == -25.0
    assert config.min_bars == 80
    assert config.min_oos_bars == 25
    assert config.min_mean_volume_quote == 50_000.0
    assert config.max_symbols == 12
    assert config.evaluate_strategies is True
    assert config.run_start_unix_seconds == 1_700_000_000
    assert config.run_end_unix_seconds == 1_800_000_000
    assert config.out_dir == tmp_path / "artifact"
    assert config.scoring.weight_oos_return == 0.3
    assert config.scoring.require_oos_return is False
    assert config.scoring.sharpe_cap == 2.5
    assert config.scoring.min_trades == 3
    assert config.scoring.max_drawdown_pct == -25.0


def test_run_opportunity_discovery_full_batch_all_resolutions_and_strategies(tmp_path: Path) -> None:
    symbols = ("btc", "eth", "sol")
    strategy_ids = ("sma_cross", "rsi_threshold", "ema_cross")
    resolutions = list(DEFAULT_RESOLUTIONS)
    expected_candidates = len(symbols) * len(resolutions) * len(strategy_ids)

    def fake_universe(**_kwargs: object) -> list[UniverseEntry]:
        return [
            UniverseEntry(
                symbol_key=symbol_key,
                market_symbol=f"{symbol_key.upper()}USDT",
                mean_volume_quote_24h=2_000_000.0,
                bar_count_sample=48,
            )
            for symbol_key in symbols
        ]

    load_calls: list[tuple[str, str]] = []

    def fake_bars(**kwargs: object) -> list[dict[str, Any]]:
        symbol_key = str(kwargs.get("symbol_key") or "")
        resolution = str(kwargs.get("resolution") or "")
        load_calls.append((symbol_key, resolution))
        return _bars(200)

    config = DiscoveryConfig(
        exchange="hyperliquid",
        symbols=list(symbols),
        resolutions=resolutions,
        strategy_ids=list(strategy_ids),
        months=2,
        use_cache=False,
        cash=15_000.0,
        fee_role="taker",
        min_trades=1,
        min_bars=100,
        min_oos_bars=20,
        max_symbols=len(symbols),
        out_dir=tmp_path,
    )
    report = run_opportunity_discovery(
        config,
        discover_universe=fake_universe,
        fetch_bars=fake_bars,
    )

    assert report["summary"]["candidates_evaluated"] == expected_candidates
    assert len(report["config"]["strategy_ids"]) == len(strategy_ids)
    assert report["config"]["resolutions"] == resolutions
    assert set(report["config"]["symbols_scanned"]) == set(symbols)
    assert (tmp_path / "discovery_report.json").is_file()
    ranked = report.get("ranked") or []
    rejected = report.get("rejected") or []
    assert len(ranked) + len(rejected) == expected_candidates
    assert len(load_calls) == len(symbols) * len(resolutions)
    assert set(load_calls) == {(symbol, resolution) for symbol in symbols for resolution in resolutions}


def test_run_market_scan_full_batch_all_resolutions(tmp_path: Path) -> None:
    symbols = ("btc", "eth")
    resolutions = list(DEFAULT_RESOLUTIONS)
    expected_candidates = len(symbols) * len(resolutions)

    def fake_universe(**_kwargs: object) -> list[UniverseEntry]:
        return [
            UniverseEntry(
                symbol_key=symbol_key,
                market_symbol=f"{symbol_key.upper()}USDT",
                mean_volume_quote_24h=750_000.0,
                bar_count_sample=24,
            )
            for symbol_key in symbols
        ]

    def fake_bars(**_kwargs: object) -> list[dict[str, Any]]:
        return _bars(150)

    config = DiscoveryConfig(
        exchange="hyperliquid",
        symbols=list(symbols),
        resolutions=resolutions,
        evaluate_strategies=False,
        min_bars=100,
        min_mean_volume_quote=100_000.0,
        max_symbols=len(symbols),
        out_dir=tmp_path,
    )
    report = run_opportunity_discovery(
        config,
        discover_universe=fake_universe,
        fetch_bars=fake_bars,
    )
    assert report["config"]["evaluate_strategies"] is False
    assert report["summary"]["candidates_evaluated"] == expected_candidates
    assert report["config"]["strategy_ids"] == []


def test_run_opportunity_discovery_logs_evaluation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_universe(**_kwargs: object) -> list[UniverseEntry]:
        return [
            UniverseEntry(
                symbol_key="btc",
                market_symbol="BTCUSDT",
                mean_volume_quote_24h=1_000_000.0,
                bar_count_sample=24,
            ),
        ]

    def fake_bars(**_kwargs: object) -> list[dict[str, Any]]:
        return _bars(200)

    def boom(**_kwargs: object) -> Any:
        raise RuntimeError("synthetic backtest failure")

    monkeypatch.setattr("traderbot.discovery.run.evaluate_discovery_candidate", boom)

    log_lines: list[str] = []
    config = DiscoveryConfig(
        exchange="hyperliquid",
        symbols=["btc"],
        resolutions=["60"],
        strategy_ids=["sma_cross"],
        months=1,
        use_cache=False,
        min_trades=1,
        min_bars=100,
        min_oos_bars=20,
        max_symbols=1,
        out_dir=tmp_path,
    )
    report = run_opportunity_discovery(
        config,
        progress=log_lines.append,
        discover_universe=fake_universe,
        fetch_bars=fake_bars,
    )
    assert report["summary"]["candidates_rejected"] == 1
    assert any("discovery: ERROR btc 60 sma_cross" in line for line in log_lines)
    assert any("evaluation error" in line for line in log_lines)


def test_discovery_job_task_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from lab.discovery_job import run_opportunity_discovery_task

    def fake_run(config: DiscoveryConfig, **kwargs: object) -> dict[str, object]:
        assert config.out_dir is not None
        config.out_dir.mkdir(parents=True, exist_ok=True)
        artifact = config.out_dir / "discovery_report.json"
        artifact.write_text("{}", encoding="utf-8")
        return {
            "summary": {"candidates_evaluated": 0, "candidates_eligible": 0, "candidates_rejected": 0},
            "config": {"scan_kind": "market_opportunity", "exchange": "hyperliquid"},
            "ranked": [],
            "rejected": [],
            "artifact_path": str(artifact),
        }

    monkeypatch.setattr("traderbot.discovery.run.run_opportunity_discovery", fake_run)
    monkeypatch.setattr("lab.store.discovery.record_discovery_run", lambda **_: "job123")
    run_opportunity_discovery_task(
        {
            "scan_kind": "market_opportunity",
            "symbols": ["btc"],
            "resolutions": ["60"],
            "evaluate_strategies": False,
            "out": str(tmp_path / "out"),
        },
        job_id="job123",
        log=lambda _: None,
    )


def test_resolve_discovery_scan_kind_routing() -> None:
    from lab.discovery_job import (
        COINBEACON_SCAN_KIND,
        HYPERLIQUID_MARKET_SCAN_KIND,
        HYPERLIQUID_STRATEGY_SCAN_KIND,
        resolve_discovery_scan_kind,
    )

    assert resolve_discovery_scan_kind({"scan_kind": "coinbeacon_market"}) == COINBEACON_SCAN_KIND
    assert resolve_discovery_scan_kind({"scan_kind": "hyperliquid"}) == HYPERLIQUID_MARKET_SCAN_KIND
    assert resolve_discovery_scan_kind({"scan_kind": "strategy_screen"}) == HYPERLIQUID_STRATEGY_SCAN_KIND
    assert (
        resolve_discovery_scan_kind(
            {"symbols": ["btc"], "resolutions": ["60"], "evaluate_strategies": False},
        )
        == HYPERLIQUID_MARKET_SCAN_KIND
    )
    assert (
        resolve_discovery_scan_kind({"symbols": ["btc"], "strategy_ids": ["sma_cross"]})
        == HYPERLIQUID_STRATEGY_SCAN_KIND
    )
    assert resolve_discovery_scan_kind({}) == COINBEACON_SCAN_KIND
