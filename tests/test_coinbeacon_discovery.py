from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from traderbot.discovery.coinbeacon_run import (
    CoinBeaconDiscoveryConfig,
    run_coinbeacon_market_discovery,
)
from traderbot.integrations.coinbeacon.client import CoinBeaconClient, CoinBeaconCredits


def _load_fixture(name: str) -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "coinbeacon" / name
    return json.loads(path.read_text(encoding="utf-8"))


class FakeCoinBeaconClient:
    def __init__(self) -> None:
        self.last_credits = CoinBeaconCredits(remaining=1500, limit=2000, cost=1)

    def get_public(self, path: str, *, params: dict[str, Any] | None = None, use_cache: bool = True) -> dict[str, Any]:
        normalized = path.strip("/")
        if normalized == "public/market/globals":
            return _load_fixture("globals.json")
        if normalized == "public/market/sentiment":
            return {"segments": [], "updatedAt": 1}
        if normalized == "public/market/structure":
            return {"basis": [], "updatedAt": 1}
        if normalized == "public/screener":
            preset = (params or {}).get("preset")
            if preset == "volume-surge":
                return _load_fixture("screener_volume_surge.json")
            return {"preset": {"id": preset}, "meta": {"matched": 0}, "rows": []}
        if normalized == "public/trend-scanner":
            return _load_fixture("trend_scanner.json")
        if normalized.startswith("public/funding/coin/"):
            return {"base": normalized.split("/")[-1], "venues": []}
        raise AssertionError(f"unexpected path {path}")


def test_run_coinbeacon_market_discovery_builds_ranked(tmp_path: Path) -> None:
    config = CoinBeaconDiscoveryConfig(
        screener_presets=["volume-surge"],
        include_context=True,
        detail_top_n=1,
        out_dir=tmp_path,
    )
    report = run_coinbeacon_market_discovery(
        config,
        client=FakeCoinBeaconClient(),  # type: ignore[arg-type]
        progress=lambda _: None,
    )
    assert report["config"]["scan_kind"] == "coinbeacon_market"
    assert report["summary"]["candidates_evaluated"] >= 2
    ranked = report["ranked"]
    assert ranked[0]["rank"] == 1
    assert "ETH" in {row["base"] for row in ranked}
    assert (tmp_path / "discovery_report.json").is_file()
    eth = next(row for row in ranked if row["base"] == "ETH")
    assert "volume-surge" in eth["preset_hits"]
