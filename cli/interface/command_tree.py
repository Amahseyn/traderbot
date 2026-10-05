from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class FlagDoc:
    name: str
    help: str


@dataclass(frozen=True, slots=True)
class SubcommandDoc:
    name: str
    summary: str
    usage: str
    flags: tuple[FlagDoc, ...] = ()


@dataclass(frozen=True, slots=True)
class TopLevelCommandDoc:
    name: str
    summary: str
    subcommands: tuple[SubcommandDoc, ...] = ()
    usage: str | None = None
    flags: tuple[FlagDoc, ...] = ()


def command_tree() -> list[dict]:
    """Static, complete CLI surface (research + terminal + root)."""
    docs: tuple[TopLevelCommandDoc, ...] = (
        TopLevelCommandDoc(
            name="(root)",
            summary="No subcommand: print Nobitex profile JSON (.env keys). --help lists commands.",
            usage="traderbot | traderbot --help",
        ),
        TopLevelCommandDoc(
            name="export",
            summary="Download Nobitex UDF OHLC to CSV (no API key).",
            usage="traderbot export --src btc --dst rls --interval D --days 90 --out data",
            flags=(
                FlagDoc("--jobs", "Batch from JSON (export.jobs*.json)."),
                FlagDoc("--symbol / --src --dst", "Single market."),
                FlagDoc("--interval", "Candle size (1, 60, D, …)."),
                FlagDoc("--days", "History length (default 30)."),
                FlagDoc("--out", "Output directory (default data)."),
                FlagDoc("--crypto-layout", "ohlc/ + horizons/ under crypto root."),
            ),
        ),
        TopLevelCommandDoc(
            name="data",
            summary="Supported markets, live UDF charts, and on-disk horizon layouts.",
            subcommands=(
                SubcommandDoc(
                    name="markets",
                    summary="JSON list of markets from export jobs (default five-source set).",
                    usage="traderbot data markets",
                    flags=(FlagDoc("--jobs", "Override export jobs JSON."),),
                ),
                SubcommandDoc(
                    name="live",
                    summary="Recent closed candles for every supported market; multi-panel PNG.",
                    usage="traderbot data live --interval 60 --bars 96",
                    flags=(
                        FlagDoc("--poll-sec", "Re-fetch and refresh (realtime watch)."),
                        FlagDoc("--show", "Interactive matplotlib window."),
                        FlagDoc("--json", "Last-close manifest only (no plots)."),
                    ),
                ),
                SubcommandDoc(
                    name="horizons",
                    summary="Copy OHLC if needed; rebuild data/crypto/horizons/*.",
                    usage="traderbot data horizons --from data/crypto/ohlc",
                    flags=(
                        FlagDoc("--from", "OHLC directory."),
                        FlagDoc("--crypto-root", "Default data/crypto."),
                    ),
                ),
                SubcommandDoc(
                    name="plots",
                    summary="List or open PNG charts from a prior run directory.",
                    usage="traderbot data plots results/strategies/compare/BTCIRT_60 --open",
                    flags=(
                        FlagDoc("--pick", "Interactive browser (category → run → strategy)."),
                        FlagDoc("--json", "Plot paths catalog."),
                        FlagDoc("--open", "System image viewer."),
                        FlagDoc("--show", "Interactive matplotlib window."),
                    ),
                ),
            ),
        ),
        TopLevelCommandDoc(
            name="backtest",
            summary="One strategy, one CSV (shortcut; see also strategy backtest).",
            usage="traderbot backtest PATH.csv --strategy sma_cross --out DIR",
            flags=(
                FlagDoc("--strategy", "Rule strategy id (strategy catalog)."),
                FlagDoc("--fast / --slow / --period / …", "Strategy params."),
                FlagDoc("--out", "JSON + optional charts."),
                FlagDoc("--visualize / --no-visualize", "Equity plots when --out set."),
            ),
        ),
        TopLevelCommandDoc(
            name="strategy",
            summary="Catalog, backtest, batch, and compare rule strategies.",
            subcommands=(
                SubcommandDoc("catalog", "List strategies.", "traderbot strategy catalog [--implemented-only]"),
                SubcommandDoc(
                    "backtest",
                    "Long-only backtest on one CSV.",
                    "traderbot strategy backtest PATH.csv --strategy ema_cross --out DIR",
                    flags=(
                        FlagDoc("--visualize", "Charts under out/visualizations/."),
                        FlagDoc("--vectorbt", "Extra risk metrics (optional extra)."),
                        FlagDoc("--context-bars", "Recent-price filters (mean rev / MACD)."),
                        FlagDoc("--price-confirm", "Trend confirmation (SMA/EMA)."),
                    ),
                ),
                SubcommandDoc(
                    "batch",
                    "One strategy on every *.csv in a directory.",
                    "traderbot strategy batch data/crypto/ohlc --strategy rsi_threshold",
                ),
                SubcommandDoc(
                    "compare",
                    "Every implemented strategy on one CSV; rank by return.",
                    "traderbot strategy compare PATH.csv --out DIR --visualize",
                    flags=(
                        FlagDoc("--out", "Experiment root (default with --visualize): runs/ + reports/compare_manifest.json."),
                        FlagDoc("--visualize", "Ranking/equity charts in visualizations/."),
                    ),
                ),
            ),
        ),
        TopLevelCommandDoc(
            name="pipeline",
            summary="Named end-to-end flows (export, strategy research) → solutions/.",
            subcommands=(
                SubcommandDoc("list", "JSON list of pipeline ids.", "traderbot pipeline list"),
                SubcommandDoc(
                    "run",
                    "Execute pipeline by id.",
                    "traderbot pipeline run crypto-1h-local [--csv ...] [--tail-bars ...]",
                    flags=(
                        FlagDoc("--data-dir", "Override CSV input directory."),
                        FlagDoc("--csv", "Required for single-asset pipelines."),
                        FlagDoc("--skip-export", "Use existing data."),
                        FlagDoc("--export-days", "History for export steps."),
                        FlagDoc("--tail-bars", "crypto-1h-local: limit to last N 1h bars."),
                        FlagDoc("--holdout-tail-bars", "crypto-1h-local: rank strategies on the last N bars."),
                        FlagDoc("--all-assets", "crypto-1h-local: every *_60.csv."),
                    ),
                ),
                SubcommandDoc(
                    "run-config",
                    "Run from experiment JSON (tracks pending/running/completed).",
                    "traderbot pipeline run-config config/experiment.crypto-1h-local.json",
                    flags=(
                        FlagDoc("--force", "Re-run completed experiments."),
                        FlagDoc("--dry-run", "Show resolved pipeline kwargs per test step."),
                        FlagDoc("--step", "Run one test_steps step_id only."),
                    ),
                ),
            ),
        ),
        TopLevelCommandDoc(
            name="interface",
            summary="Discover and run pickable CLI actions (this module).",
            subcommands=(
                SubcommandDoc("catalog", "Full JSON catalog.", "traderbot interface catalog"),
                SubcommandDoc("list", "Pickable ids (filter --kind / --tag).", "traderbot interface list"),
                SubcommandDoc("describe", "One pickable by id.", "traderbot interface describe workflow/download-multisource"),
                SubcommandDoc(
                    "pick",
                    "Interactive or --id selection; --run executes.",
                    "traderbot interface pick [--run]",
                ),
                SubcommandDoc("run", "Execute pickable by id.", "traderbot interface run strategy/compare-btc60"),
            ),
        ),
        TopLevelCommandDoc(
            name="terminal",
            summary="Live UDF polling, once, CSV replay (paper default).",
            subcommands=(
                SubcommandDoc("catalog", "Commands + strategies.", "traderbot terminal catalog"),
                SubcommandDoc(
                    "run",
                    "Poll for new candles (.env for Nobitex).",
                    "traderbot terminal run --src btc --dst rls --interval 60 --strategy sma_cross",
                ),
                SubcommandDoc("once", "Latest closed candle once.", "traderbot terminal once --strategy ema_cross"),
                SubcommandDoc(
                    "replay",
                    "Walk CSV bar-by-bar.",
                    "traderbot terminal replay PATH.csv --strategy macd_cross",
                ),
            ),
        ),
    )
    return [asdict(d) for d in docs]
