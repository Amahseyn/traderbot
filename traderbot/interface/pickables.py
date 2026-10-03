from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from traderbot.pipelines.registry import list_pipelines

CRYPTO_1H_JOBS = "export.jobs.crypto-1h.json"
CRYPTO_1H_OHLC_CSVS: tuple[str, ...] = (
    "data/crypto/ohlc/BTCIRT_60.csv",
    "data/crypto/ohlc/ETHIRT_60.csv",
    "data/crypto/ohlc/ETHUSDT_60.csv",
    "data/crypto/ohlc/XRPIRT_60.csv",
    "data/crypto/ohlc/LTCIRT_60.csv",
)


def _strategy_compare_steps_for_crypto_1h() -> tuple[tuple[str, ...], ...]:
    steps: list[tuple[str, ...]] = []
    for csv_rel in CRYPTO_1H_OHLC_CSVS:
        stem = Path(csv_rel).stem
        steps.append(
            (
                "strategy",
                "compare",
                csv_rel,
                "--out",
                f"results/strategies/compare/{stem}",
                "--visualize",
            )
        )
    return tuple(steps)


@dataclass(frozen=True, slots=True)
class Pickable:
    """One selectable action; invocations are argv tokens after ``traderbot``."""

    id: str
    kind: str
    title: str
    summary: str
    invocations: tuple[tuple[str, ...], ...]
    tags: tuple[str, ...] = ()


def _workflow(
    slug: str,
    title: str,
    summary: str,
    *steps: tuple[str, ...],
    tags: tuple[str, ...] = (),
) -> Pickable:
    return Pickable(
        id=f"workflow/{slug}",
        kind="workflow",
        title=title,
        summary=summary,
        invocations=steps,
        tags=("workflow", *tags),
    )


def _invoke(
    slug: str,
    title: str,
    summary: str,
    argv: tuple[str, ...],
    *,
    kind = "command",
    tags: tuple[str, ...] = (),
) -> Pickable:
    return Pickable(
        id=f"{kind}/{slug}",
        kind=kind,
        title=title,
        summary=summary,
        invocations=(argv,),
        tags=tags,
    )


def all_pickables() -> list[Pickable]:
    pipelines = list_pipelines()
    pipeline_picks = [
        _invoke(
            f"run/{p.id}",
            p.title,
            p.description,
            ("pipeline", "run", p.id),
            kind="pipeline",
            tags=("pipeline", "ml", "export"),
        )
        for p in pipelines
    ]
    return [
        _invoke(
            "auth/check",
            "Verify API key in .env",
            "Signed GET /users/profile.",
            ("auth", "check"),
            tags=("api", "auth"),
        ),
        _invoke(
            "auth/apikeys-list",
            "List Nobitex API keys",
            "Requires NOBITEX_AUTH_TOKEN from auth login.",
            ("auth", "apikeys", "list"),
            tags=("api", "auth"),
        ),
        _invoke(
            "export/single-market",
            "Export one market (daily)",
            "Public UDF download; no API key.",
            ("export", "--src", "btc", "--dst", "rls", "--interval", "D", "--days", "90", "--out", "data"),
            tags=("data", "export"),
        ),
        _invoke(
            "export/jobs-five-sources",
            "Export five crypto markets (all intervals)",
            "Uses export.jobs.5sources.json; writes data/crypto layout when --out data/crypto.",
            ("export", "--jobs", "export.jobs.5sources.json", "--out", "data/crypto"),
            tags=("data", "export"),
        ),
        _invoke(
            "data/markets",
            "List supported Nobitex markets",
            "Derived from export.jobs.5sources.json (BTC, ETH, XRP, LTC, …).",
            ("data", "markets"),
            tags=("data", "live"),
        ),
        _invoke(
            "data/markets-crypto-1h",
            "List crypto markets (1h jobs file)",
            "Same as data markets but scoped to export.jobs.crypto-1h.json (five assets, interval 60).",
            ("data", "markets", "--jobs", CRYPTO_1H_JOBS),
            tags=("data", "live"),
        ),
        _invoke(
            "export/jobs-crypto-1h",
            "Export crypto markets (1h only)",
            "Five Nobitex pairs at UDF interval 60 → data/crypto/ohlc.",
            ("export", "--jobs", CRYPTO_1H_JOBS, "--out", "data/crypto"),
            tags=("data", "export"),
        ),
        _invoke(
            "data/live-charts",
            "Live multi-market price dashboard",
            "Public UDF; PNG grid under results/data/live/visualizations/.",
            ("data", "live", "--interval", "60", "--bars", "96", "--out", "results/data/live"),
            tags=("data", "live", "visualization"),
        ),
        _invoke(
            "data/live-watch",
            "Watch live markets (refresh every 60s)",
            "Re-fetch all markets and rewrite dashboard PNG.",
            (
                "data",
                "live",
                "--interval",
                "60",
                "--bars",
                "48",
                "--out",
                "results/data/live",
                "--poll-sec",
                "60",
            ),
            tags=("data", "live", "visualization"),
        ),
        _invoke(
            "data/horizons",
            "Rebuild horizon slices from OHLC",
            "Materialize data/crypto/horizons/* from existing CSVs.",
            ("data", "horizons", "--from", "data/crypto/ohlc"),
            tags=("data",),
        ),
        _invoke(
            "data/plots-compare",
            "Open charts from strategy compare results",
            "Lists PNGs under results/strategies/compare/BTCIRT_60 (use --open to view).",
            (
                "data",
                "plots",
                "results/strategies/compare/BTCIRT_60",
                "--open",
            ),
            tags=("data", "visualization"),
        ),
        _invoke(
            "strategy/catalog",
            "List implemented strategies",
            "JSON catalog of rule strategies for backtest and terminal.",
            ("strategy", "catalog", "--implemented-only"),
            tags=("strategy",),
        ),
        _invoke(
            "strategy/compare-btc60",
            "Compare all strategies on BTC 1h with charts",
            "Writes results/strategies/compare/BTCIRT_60 and visualization/ when matplotlib available.",
            (
                "strategy",
                "compare",
                "data/crypto/ohlc/BTCIRT_60.csv",
                "--out",
                "results/strategies/compare/BTCIRT_60",
                "--visualize",
            ),
            tags=("strategy", "visualization"),
        ),
        _invoke(
            "strategy/backtest-sma",
            "SMA cross backtest (top-level backtest)",
            "Same as traderbot backtest with explicit SMA params.",
            (
                "backtest",
                "data/crypto/ohlc/BTCIRT_60.csv",
                "--strategy",
                "sma_cross",
                "--fast",
                "5",
                "--slow",
                "20",
                "--out",
                "results/strategies/backtest/btc_sma_cross",
                "--visualize",
            ),
            tags=("strategy", "visualization"),
        ),
        _invoke(
            "ml/catalog",
            "List implemented forecast models",
            "JSON catalog (lightgbm, chronos, …).",
            ("ml", "catalog", "--implemented-only"),
            tags=("ml",),
        ),
        _invoke(
            "ml/run-lightgbm-btc60",
            "LightGBM eval on BTC 1h CSV",
            "Single run with plots under results/ml.",
            (
                "ml",
                "run",
                "data/crypto/ohlc/BTCIRT_60.csv",
                "--model",
                "lightgbm",
            ),
            tags=("ml", "visualization"),
        ),
        _invoke(
            "ml/batch-4h-all-horizons",
            "LightGBM batch on 4h horizon folder",
            "Every CSV in folder; all default forecast horizons.",
            (
                "ml",
                "batch",
                "data/crypto/horizons/4h",
                "--model",
                "lightgbm",
                "--all-horizons",
            ),
            tags=("ml", "visualization"),
        ),
        _invoke(
            "ml/batch-lightgbm-crypto-1h",
            "LightGBM batch on crypto 1h folder",
            "Default 1h forecast horizon per asset under data/crypto/horizons/1h.",
            (
                "ml",
                "batch",
                "data/crypto/horizons/1h",
                "--model",
                "lightgbm",
            ),
            tags=("ml", "visualization"),
        ),
        _invoke(
            "pipeline/list",
            "List named pipelines",
            "End-to-end flows into solutions/.",
            ("pipeline", "list"),
            tags=("pipeline",),
        ),
        _invoke(
            "interface/catalog",
            "Full CLI catalog JSON",
            "This document: command tree, pickables, strategies, models.",
            ("interface", "catalog"),
            tags=("meta",),
        ),
        _invoke(
            "terminal/catalog",
            "Terminal (live/replay) catalog",
            "Paper/live execution; separate from research export/ML.",
            ("terminal", "catalog", "--implemented-only"),
            tags=("terminal",),
        ),
        _invoke(
            "terminal/replay-csv",
            "Replay strategy on OHLC CSV",
            "Bar-by-bar signals; no API key.",
            (
                "terminal",
                "replay",
                "data/crypto/ohlc/BTCIRT_60.csv",
                "--strategy",
                "sma_cross",
            ),
            tags=("terminal",),
        ),
        _workflow(
            "download-multisource",
            "Download five markets + horizon slices",
            "Export jobs file then rebuild horizons/.",
            ("export", "--jobs", "export.jobs.5sources.json", "--out", "data/crypto"),
            ("data", "horizons", "--from", "data/crypto/ohlc"),
            tags=("data", "export"),
        ),
        _workflow(
            "strategy-compare-charts",
            "Compare strategies with charts",
            "Rank implementations on one CSV.",
            (
                "strategy",
                "compare",
                "data/crypto/ohlc/BTCIRT_60.csv",
                "--out",
                "results/strategies/compare/BTCIRT_60",
                "--visualize",
            ),
            tags=("strategy", "visualization"),
        ),
        _workflow(
            "ml-all-horizons-4h",
            "ML batch all horizons (4h folder)",
            "LightGBM on every CSV in horizons/4h.",
            (
                "ml",
                "batch",
                "data/crypto/horizons/4h",
                "--model",
                "lightgbm",
                "--all-horizons",
            ),
            tags=("ml", "visualization"),
        ),
        _workflow(
            "compare-all-strategies-crypto-1h",
            "Compare all strategies on every crypto 1h CSV",
            "Backtest every implemented strategy on each five-market 1h file; charts under results/strategies/compare/.",
            *_strategy_compare_steps_for_crypto_1h(),
            tags=("strategy", "visualization"),
        ),
        _workflow(
            "crypto-1h-local-research",
            "Crypto 1h local: all strategies + LightGBM",
            "No download; full on-disk *_60.csv per asset (use pipeline --tail-bars 24 only for smoke).",
            ("pipeline", "run", "crypto-1h-local", "--all-assets"),
            tags=("strategy", "ml", "visualization"),
        ),
        _invoke(
            "experiment/run-crypto-1h-local",
            "Run crypto 1h experiment (config file)",
            "Uses config/experiment.crypto-1h-local.json; updates status pending→completed.",
            ("pipeline", "run-config", "config/experiment.crypto-1h-local.json"),
            tags=("pipeline", "strategy", "ml", "experiment"),
        ),
        _invoke(
            "experiment/run-crypto-1h-smoke",
            "Run crypto 1h smoke experiment (config)",
            "Uses config/experiment.crypto-1h-smoke.json (BTC, 24 bars, default LightGBM).",
            ("pipeline", "run-config", "config/experiment.crypto-1h-smoke.json"),
            tags=("pipeline", "strategy", "experiment"),
        ),
        *pipeline_picks,
    ]


_PICKABLE_BY_ID: dict[str, Pickable] | None = None


def pickable_by_id(pick_id: str) -> Pickable:
    global _PICKABLE_BY_ID
    if _PICKABLE_BY_ID is None:
        _PICKABLE_BY_ID = {p.id: p for p in all_pickables()}
    if pick_id not in _PICKABLE_BY_ID:
        raise KeyError(pick_id)
    return _PICKABLE_BY_ID[pick_id]


def pickable_to_dict(p: Pickable) -> dict:
    return {
        **asdict(p),
        "cli": ["traderbot", *p.invocations[0]] if p.invocations else ["traderbot"],
        "cli_steps": [["traderbot", *step] for step in p.invocations],
    }


def list_pickable_dicts(*, kind: str | None = None, tag: str | None = None) -> list[dict]:
    rows: list[dict] = []
    for p in all_pickables():
        if kind is not None and p.kind != kind:
            continue
        if tag is not None and tag not in p.tags:
            continue
        rows.append(
            {
                "id": p.id,
                "kind": p.kind,
                "title": p.title,
                "summary": p.summary,
                "tags": list(p.tags),
            }
        )
    return rows
