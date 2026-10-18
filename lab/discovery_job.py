from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from traderbot.discovery.coinbeacon_run import (
    coinbeacon_discovery_config_from_body,
    run_coinbeacon_market_discovery,
)
from traderbot.discovery.run import discovery_config_from_body, run_opportunity_discovery
from traderbot.integrations.coinbeacon.client import CoinBeaconError, coinbeacon_api_key_configured

COINBEACON_SCAN_KIND = "coinbeacon_market"
HYPERLIQUID_MARKET_SCAN_KIND = "market_opportunity"
HYPERLIQUID_STRATEGY_SCAN_KIND = "strategy_screen"


def resolve_discovery_scan_kind(body: dict[str, Any]) -> str:
    """Pick CoinBeacon vs Hyperliquid engine from explicit scan_kind or job fields."""
    raw = str(body.get("scan_kind") or "").strip().lower()
    aliases = {
        "hyperliquid": HYPERLIQUID_MARKET_SCAN_KIND,
        "hyperliquid_market": HYPERLIQUID_MARKET_SCAN_KIND,
        "hyperliquid_strategy": HYPERLIQUID_STRATEGY_SCAN_KIND,
    }
    if raw in aliases:
        return aliases[raw]
    if raw in (COINBEACON_SCAN_KIND, HYPERLIQUID_MARKET_SCAN_KIND, HYPERLIQUID_STRATEGY_SCAN_KIND):
        return raw
    if (
        body.get("symbols")
        or body.get("resolutions")
        or body.get("strategy_ids") is not None
        or body.get("months") is not None
        or body.get("max_symbols") is not None
    ):
        if body.get("evaluate_strategies") is False:
            return HYPERLIQUID_MARKET_SCAN_KIND
        return HYPERLIQUID_STRATEGY_SCAN_KIND
    return COINBEACON_SCAN_KIND


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _discovery_out_dir(body: dict[str, Any], job_id: str | None) -> Path:
    out = body.get("out")
    if out:
        return Path(str(out))
    if job_id:
        return Path("results") / "discovery" / job_id
    return Path("results") / "discovery" / "manual"


def _run_coinbeacon_discovery(
    body: dict[str, Any],
    *,
    job_id: str | None,
    writer: Callable[[str], None],
) -> dict[str, Any]:
    if not coinbeacon_api_key_configured():
        raise CoinBeaconError(
            "No CoinBeacon API keys on the Lab API host. Set COINBEACON_API_KEY, "
            "COINBEACON_API_KEY_ALT, or COINBEACON_API_KEYS (comma-separated) in repo "
            ".env and restart ./run-lab-api.sh",
        )
    config = coinbeacon_discovery_config_from_body(body)
    config.out_dir = _discovery_out_dir(body, job_id)
    return run_coinbeacon_market_discovery(config, progress=writer)


def _run_hyperliquid_discovery(
    body: dict[str, Any],
    *,
    job_id: str | None,
    writer: Callable[[str], None],
) -> dict[str, Any]:
    merged = dict(body)
    merged["exchange"] = "hyperliquid"
    scan_kind = resolve_discovery_scan_kind(body)
    if scan_kind == HYPERLIQUID_MARKET_SCAN_KIND:
        merged["evaluate_strategies"] = False
    config = discovery_config_from_body(merged)
    config.out_dir = _discovery_out_dir(body, job_id)
    return run_opportunity_discovery(config, progress=writer)


def run_opportunity_discovery_task(
    body: dict[str, Any],
    *,
    job_id: str | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    writer = log or (lambda message: print(message, flush=True))
    scan_kind = resolve_discovery_scan_kind(body)
    if scan_kind == COINBEACON_SCAN_KIND:
        report = _run_coinbeacon_discovery(body, job_id=job_id, writer=writer)
    else:
        writer(f"discovery: hyperliquid scan ({scan_kind})")
        report = _run_hyperliquid_discovery(body, job_id=job_id, writer=writer)

    artifact_path = report.get("artifact_path")
    if artifact_path:
        writer(f"discovery: wrote {artifact_path}")

    from lab.store.discovery import record_discovery_run

    record_body = dict(body)
    record_body.setdefault("scan_kind", report.get("config", {}).get("scan_kind") or scan_kind)

    record_discovery_run(
        job_id=job_id,
        body=record_body,
        report=report,
        artifact_path=str(artifact_path) if artifact_path else None,
        finished_at_utc=_utc_now(),
    )
    writer(
        "discovery: summary "
        f"evaluated={report['summary']['candidates_evaluated']} "
        f"eligible={report['summary']['candidates_eligible']} "
        f"rejected={report['summary']['candidates_rejected']}",
    )
    writer(json.dumps(report["summary"], indent=2))
    return report
