from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from traderbot.integrations.coinbeacon.client import CoinBeaconClient, CoinBeaconError
from traderbot.integrations.coinbeacon.paths import (
    DEFAULT_SCREENER_PRESETS,
    DEFAULT_TREND_EXCHANGE,
    DEFAULT_TREND_QUOTE,
    DEFAULT_TREND_SORT,
    TREND_SORT_TIMEFRAMES,
)

CREDIT_RESERVE = 50


@dataclass
class CoinBeaconDiscoveryConfig:
    exchange: str = DEFAULT_TREND_EXCHANGE
    trend_sort: str = DEFAULT_TREND_SORT
    trend_dir: str = "desc"
    trend_quote: str = DEFAULT_TREND_QUOTE
    screener_presets: list[str] = field(default_factory=lambda: list(DEFAULT_SCREENER_PRESETS))
    include_context: bool = True
    detail_top_n: int = 12
    credit_reserve: int = CREDIT_RESERVE
    out_dir: Path | None = None


def coinbeacon_discovery_config_from_body(body: dict[str, Any]) -> CoinBeaconDiscoveryConfig:
    presets_raw = body.get("screener_presets")
    presets: list[str] = list(DEFAULT_SCREENER_PRESETS)
    if isinstance(presets_raw, list) and presets_raw:
        presets = [str(item).strip() for item in presets_raw if str(item).strip()]
    trend_sort = str(body.get("trend_sort") or DEFAULT_TREND_SORT).strip()
    if trend_sort not in TREND_SORT_TIMEFRAMES:
        trend_sort = DEFAULT_TREND_SORT
    out = body.get("out")
    return CoinBeaconDiscoveryConfig(
        exchange=str(body.get("exchange") or DEFAULT_TREND_EXCHANGE).strip(),
        trend_sort=trend_sort,
        trend_dir=str(body.get("trend_dir") or "desc").strip().lower(),
        trend_quote=str(body.get("trend_quote") or DEFAULT_TREND_QUOTE).strip().upper(),
        screener_presets=presets,
        include_context=body.get("include_context", True) is not False,
        detail_top_n=max(0, int(body.get("detail_top_n") or 12)),
        credit_reserve=int(body.get("credit_reserve") or CREDIT_RESERVE),
        out_dir=Path(str(out)) if out else None,
    )


def base_from_symbol(symbol: str) -> str:
    upper = symbol.upper().strip()
    for quote in ("USDT", "USDC", "FDUSD", "BTC", "ETH"):
        if upper.endswith(quote) and len(upper) > len(quote):
            return upper[: -len(quote)]
    return upper


def _trend_score(item: dict[str, Any], timeframe: str) -> float | None:
    scores = item.get("scores")
    if not isinstance(scores, dict):
        return None
    block = scores.get(timeframe)
    if not isinstance(block, dict):
        return None
    raw = block.get("score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _merge_ranked_rows(
    *,
    trend_payload: dict[str, Any],
    screener_runs: list[dict[str, Any]],
    trend_sort: str,
) -> list[dict[str, Any]]:
    by_base: dict[str, dict[str, Any]] = {}

    items = trend_payload.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "")
            base = base_from_symbol(symbol)
            trend_score = _trend_score(item, trend_sort)
            by_base[base] = {
                "base": base,
                "symbol": symbol,
                "exchange": item.get("exchange"),
                "price": item.get("price"),
                "trend_score": trend_score,
                "trend_score_1d": _trend_score(item, "1d"),
                "trend_score_4h": _trend_score(item, "4h"),
                "preset_hits": [],
                "volume24h": None,
                "pctChange_h24": None,
                "marketCap": None,
                "rank_cmc": None,
                "sources": ["trend_scanner"],
            }

    for run in screener_runs:
        preset_id = (run.get("preset") or {}).get("id") if isinstance(run.get("preset"), dict) else None
        rows = run.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            base = str(row.get("base") or "").upper()
            if not base:
                continue
            entry = by_base.setdefault(
                base,
                {
                    "base": base,
                    "symbol": row.get("symbol"),
                    "exchange": row.get("venue"),
                    "price": row.get("price"),
                    "trend_score": None,
                    "trend_score_1d": None,
                    "trend_score_4h": None,
                    "preset_hits": [],
                    "volume24h": None,
                    "pctChange_h24": None,
                    "marketCap": None,
                    "rank_cmc": None,
                    "sources": [],
                },
            )
            if preset_id and preset_id not in entry["preset_hits"]:
                entry["preset_hits"].append(preset_id)
            if "screener" not in entry["sources"]:
                entry["sources"].append("screener")
            volume = row.get("volume24h")
            if volume is not None:
                entry["volume24h"] = volume
            change = row.get("pctChange.h24")
            if change is not None:
                entry["pctChange_h24"] = change
            if row.get("marketCap") is not None:
                entry["marketCap"] = row.get("marketCap")
            if row.get("rank") is not None:
                entry["rank_cmc"] = row.get("rank")

    volumes = [
        float(entry["volume24h"])
        for entry in by_base.values()
        if entry.get("volume24h") is not None
    ]
    max_volume = max(volumes) if volumes else 0.0

    ranked: list[dict[str, Any]] = []
    for entry in by_base.values():
        trend_component = 0.0
        if entry.get("trend_score") is not None:
            trend_component = max(0.0, (float(entry["trend_score"]) + 100.0) / 200.0)
        volume_component = 0.0
        if entry.get("volume24h") is not None and max_volume > 0:
            volume_component = min(1.0, float(entry["volume24h"]) / max_volume)
        preset_component = min(1.0, len(entry["preset_hits"]) / max(1, len(screener_runs)))
        composite = round(0.45 * trend_component + 0.35 * volume_component + 0.20 * preset_component, 6)
        entry["composite_score"] = composite
        entry["validation_status"] = "eligible"
        entry["symbol_key"] = entry["base"].lower()
        entry["resolution"] = trend_sort
        entry["strategy_id"] = None
        entry["params_source"] = "coinbeacon_market"
        ranked.append(entry)

    ranked.sort(
        key=lambda row: (
            row.get("composite_score") is None,
            -(float(row["composite_score"]) if row.get("composite_score") is not None else 0.0),
        ),
    )
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked


def _check_credits(
    client: CoinBeaconClient,
    config: CoinBeaconDiscoveryConfig,
    log: Callable[[str], None],
) -> None:
    credits = client.last_credits
    if credits is None or credits.remaining is None:
        return
    if credits.remaining < config.credit_reserve:
        if client.rotate_if_credits_low(config.credit_reserve):
            log(
                f"discovery: coinbeacon low credits ({credits.remaining}); "
                f"using alternate API key ({client.active_key_index + 1}/{client.api_key_count})",
            )
            return
        raise CoinBeaconError(
            f"CoinBeacon credits remaining ({credits.remaining}) below reserve ({config.credit_reserve}) "
            f"on all configured keys",
        )


def run_coinbeacon_market_discovery(
    config: CoinBeaconDiscoveryConfig,
    *,
    client: CoinBeaconClient | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = progress or (lambda _message: None)
    api = client or CoinBeaconClient(min_credits_remaining=config.credit_reserve)
    key_count = getattr(api, "api_key_count", 1)
    if key_count > 1:
        log(f"discovery: coinbeacon {key_count} API key(s) configured (auto-failover)")
    estimated_cost = 5 + len(config.screener_presets) * 5
    if config.include_context:
        estimated_cost += 3
    estimated_cost += config.detail_top_n

    context: dict[str, Any] = {}
    if config.include_context:
        log("discovery: coinbeacon market globals")
        context["globals"] = api.get_public("public/market/globals")
        _check_credits(api, config, log)
        log("discovery: coinbeacon market sentiment")
        context["sentiment"] = api.get_public("public/market/sentiment")
        _check_credits(api, config, log)
        log("discovery: coinbeacon market structure")
        context["structure"] = api.get_public("public/market/structure")
        _check_credits(api, config, log)

    screener_runs: list[dict[str, Any]] = []
    for preset_id in config.screener_presets:
        _check_credits(api, config, log)
        log(f"discovery: coinbeacon screener preset={preset_id}")
        payload = api.get_public("public/screener", params={"preset": preset_id})
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        matched = meta.get("matched", 0)
        log(f"discovery: coinbeacon preset {preset_id} matched={matched}")
        if api.last_credits and api.last_credits.remaining is not None:
            log(f"discovery: coinbeacon credits remaining={api.last_credits.remaining}")
        screener_runs.append(payload)

    log(f"discovery: coinbeacon trend-scanner exchange={config.exchange} sort={config.trend_sort}")
    trend_payload = api.get_public(
        "public/trend-scanner",
        params={
            "exchange": config.exchange,
            "sort": config.trend_sort,
            "dir": config.trend_dir,
            "quote": config.trend_quote,
        },
    )
    _check_credits(api, config, log)

    ranked = _merge_ranked_rows(
        trend_payload=trend_payload,
        screener_runs=screener_runs,
        trend_sort=config.trend_sort,
    )

    coin_details: dict[str, Any] = {}
    for row in ranked[: config.detail_top_n]:
        base = str(row.get("base") or "").upper()
        if not base or base in coin_details:
            continue
        _check_credits(api, config, log)
        log(f"discovery: coinbeacon funding coin={base}")
        try:
            coin_details[base] = {
                "funding": api.get_public(f"public/funding/coin/{base}"),
            }
        except CoinBeaconError as exc:
            coin_details[base] = {"funding_error": str(exc)}

    body_config = {
        "scan_kind": "coinbeacon_market",
        "exchange": config.exchange,
        "trend_sort": config.trend_sort,
        "trend_dir": config.trend_dir,
        "trend_quote": config.trend_quote,
        "screener_presets": list(config.screener_presets),
        "include_context": config.include_context,
        "detail_top_n": config.detail_top_n,
        "evaluate_strategies": False,
    }

    credits_block: dict[str, Any] = {
        "estimated_cost": estimated_cost,
    }
    if api.last_credits:
        credits_block["remaining"] = api.last_credits.remaining
        credits_block["limit"] = api.last_credits.limit

    report: dict[str, Any] = {
        "config": body_config,
        "context": context,
        "screener": {"presets": screener_runs},
        "trend_scanner": trend_payload,
        "ranked": ranked,
        "rejected": [],
        "coin_details": coin_details,
        "credits": credits_block,
        "summary": {
            "candidates_evaluated": len(ranked),
            "candidates_eligible": len(ranked),
            "candidates_rejected": 0,
        },
    }

    if config.out_dir is not None:
        config.out_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = config.out_dir / "discovery_report.json"
        artifact_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact_path"] = str(artifact_path)

    return report
