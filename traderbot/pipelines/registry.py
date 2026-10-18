from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from traderbot.pipelines.base import PipelineFn, PipelineResult
from traderbot.pipelines.definitions import (
    pipeline_crypto_1h_local,
    pipeline_export_then_hourly,
    pipeline_crypto_jobs_export,
    pipeline_finrl_platform,
    pipeline_sma_backtest,
    pipeline_wondertrader_platform,
)
from traderbot.pipelines.market_research import (
    pipeline_full_universe_research,
    pipeline_single_market_research,
)


@dataclass(frozen=True, slots=True)
class PipelineStepView:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class PipelineChoice:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class PipelineInputView:
    """Form field the Lab UI sends with ``POST /api/jobs/pipeline-run``."""

    key: str
    label: str
    kind: str
    required: bool = False
    default: str = ""
    hint: str = ""
    options: tuple[PipelineChoice, ...] = ()


_HORIZON_CHOICES = (
    PipelineChoice("usual", "Usual for this file"),
    PipelineChoice("all", "Every horizon"),
    PipelineChoice("1m", "1 minute"),
    PipelineChoice("5m", "5 minutes"),
    PipelineChoice("1h", "1 hour"),
    PipelineChoice("2h", "2 hours"),
    PipelineChoice("4h", "4 hours"),
    PipelineChoice("6h", "6 hours"),
    PipelineChoice("12h", "12 hours"),
    PipelineChoice("1d", "1 day"),
)

_HOURLY_HORIZON_CHOICES = tuple(
    choice for choice in _HORIZON_CHOICES if choice.value not in ("usual", "all", "1m", "5m")
)


def _horizon_input(default: str, *, choices: tuple[PipelineChoice, ...] = _HORIZON_CHOICES) -> PipelineInputView:
    return PipelineInputView(
        key="horizon",
        label="Horizon",
        kind="select",
        default=default,
        hint="How far ahead to score.",
        options=choices,
    )


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    id: str
    title: str
    description: str
    fn: PipelineFn
    steps: tuple[PipelineStepView, ...] = ()
    inputs: tuple[PipelineInputView, ...] = ()
    days_kw: str | None = None
    full: bool = False


def _steps(*pairs: tuple[str, str]) -> tuple[PipelineStepView, ...]:
    return tuple(PipelineStepView(step_id, title) for step_id, title in pairs)


PIPELINES: tuple[PipelineSpec, ...] = (
    PipelineSpec(
        id="crypto-jobs-export",
        title="Export crypto 1h jobs",
        description="Nobitex OHLC from export jobs JSON → data/crypto (default jobs file).",
        fn=pipeline_crypto_jobs_export,
        steps=_steps(("export", "Download jobs file"), ("write", "Write OHLC files")),
        inputs=(
            PipelineInputView(
                key="days",
                label="Days",
                kind="number",
                default="90",
                hint="How many days of OHLC to pull from Nobitex.",
            ),
        ),
        days_kw="days",
    ),
    PipelineSpec(
        id="sma-backtest",
        title="SMA backtest",
        description="Rule-based SMA cross backtest on one CSV.",
        fn=pipeline_sma_backtest,
        steps=_steps(("load", "Load one file"), ("backtest", "SMA cross"), ("summary", "Write summary")),
        inputs=(
            PipelineInputView(
                key="dataset",
                label="Price file",
                kind="dataset",
                required=True,
            ),
            PipelineInputView(key="fast", label="Fast window", kind="number", default="5", hint="Short moving average, in bars."),
            PipelineInputView(key="slow", label="Slow window", kind="number", default="20", hint="Long moving average, in bars."),
        ),
    ),
    PipelineSpec(
        id="crypto-1h-local",
        title="Crypto 1h local (no export)",
        description="Full on-disk *_60.csv per asset (or --tail-bars); compare all rule-based strategies.",
        fn=pipeline_crypto_1h_local,
        steps=_steps(
            ("slice", "Hourly files on disk"),
            ("compare", "Compare strategies"),
        ),
        inputs=(
            PipelineInputView(
                key="all_assets",
                label="Every hourly file",
                kind="boolean",
                default="true",
                hint="Uses *_60.csv already under data/. Uncheck to pick one file.",
            ),
            PipelineInputView(
                key="dataset",
                label="Hourly file",
                kind="dataset",
                hint="Used only when “Every hourly file” is off.",
            ),
            _horizon_input("1h", choices=_HOURLY_HORIZON_CHOICES),
        ),
        full=True,
    ),
    PipelineSpec(
        id="full-research-strategies",
        title="Download, then strategies only",
        description="Export crypto 1h jobs, then compare rule-based strategies on each hourly file.",
        fn=lambda **kwargs: pipeline_export_then_hourly(
            pipeline_id="full-research-strategies",
            title="Download, then strategies only",
            description="Export crypto 1h jobs, then compare rule-based strategies.",
            **kwargs,
        ),
        steps=_steps(
            ("export", "Download jobs file"),
            ("compare", "Compare strategies"),
        ),
        inputs=(
            PipelineInputView(
                key="days",
                label="Export days",
                kind="number",
                default="90",
                hint="Download window before the strategy compare.",
            ),
            PipelineInputView(
                key="all_assets",
                label="Every hourly file",
                kind="boolean",
                default="true",
                hint="After the download, compare every hourly file. Uncheck to pick one.",
            ),
            PipelineInputView(
                key="dataset",
                label="Hourly file",
                kind="dataset",
                hint="Used only when “Every hourly file” is off.",
            ),
        ),
        days_kw="export_days",
        full=True,
    ),
    PipelineSpec(
        id="finrl-platform",
        title="FinRL + Hyperliquid (full platform)",
        description=(
            "Export HL 1m/5m → FinRL intraday window report (100 bars, not annualized) → "
            "traderbot finrl_ema_intraday backtest → optional FinRL adaptive rotation (US equity)."
        ),
        fn=pipeline_finrl_platform,
        steps=_steps(
            ("export", "Hyperliquid OHLC"),
            ("finrl_intraday", "FinRL intraday experiment"),
            ("traderbot_backtest", "Traderbot finrl_ema_intraday"),
            ("equity_rotation", "FinRL adaptive rotation (optional)"),
        ),
        inputs=(
            PipelineInputView(key="src", label="Coin (HL)", kind="text", default="btc"),
            PipelineInputView(key="dst", label="Quote", kind="text", default="usdt"),
            PipelineInputView(
                key="intervals",
                label="Intervals",
                kind="text",
                default="1,5",
                hint="Hyperliquid resolutions: 1,5,15,...",
            ),
            PipelineInputView(
                key="max_bars",
                label="Bars per interval",
                kind="number",
                default="100",
                hint="Window size; metrics are not annualized.",
            ),
            PipelineInputView(
                key="equity_periods",
                label="Equity rotation periods",
                kind="number",
                default="100",
                hint="Weekly rebalance count for FinRL adaptive rotation report.",
            ),
            PipelineInputView(
                key="include_equity_rotation",
                label="Run US equity rotation",
                kind="boolean",
                default="true",
            ),
        ),
        full=True,
    ),
    PipelineSpec(
        id="single-market-research",
        title="Single market: export → Optuna → compare",
        description=(
            "Hyperliquid (or Nobitex) OHLC for one symbol across intervals, "
            "Optuna-tune every rule-based strategy, then compare on the same data."
        ),
        fn=pipeline_single_market_research,
        steps=_steps(
            ("export", "Download OHLC"),
            ("optimize", "Optuna per strategy × interval"),
            ("compare", "Rank strategies"),
        ),
        inputs=(
            PipelineInputView(
                key="market_symbol",
                label="Market symbol",
                kind="text",
                default="BTCUSDT",
                required=True,
            ),
            PipelineInputView(
                key="intervals",
                label="Intervals",
                kind="text",
                default="1,5,15,60",
                hint="Comma-separated HL resolutions.",
            ),
            PipelineInputView(
                key="export_days",
                label="Export days",
                kind="number",
                default="30",
            ),
            PipelineInputView(
                key="optimize_n_trials",
                label="Optuna trials",
                kind="number",
                default="80",
            ),
            PipelineInputView(
                key="exchange",
                label="Exchange",
                kind="text",
                default="hyperliquid",
            ),
        ),
        full=True,
    ),
    PipelineSpec(
        id="full-universe-research",
        title="Universe: all strategies × many markets",
        description=(
            "Batch export for top Hyperliquid perps (or jobs file), Optuna all backtest strategies "
            "on each file, then strategy compare. Long-running — tune top_markets and trials."
        ),
        fn=pipeline_full_universe_research,
        steps=_steps(
            ("export", "Batch OHLC"),
            ("optimize", "Optuna all strategies"),
            ("compare", "Per-file compare"),
        ),
        inputs=(
            PipelineInputView(
                key="top_markets",
                label="Top markets",
                kind="number",
                default="30",
                hint="From HL universe or export jobs file.",
            ),
            PipelineInputView(
                key="intervals",
                label="Intervals",
                kind="text",
                default="1,5,15,60",
            ),
            PipelineInputView(
                key="export_days",
                label="Export days",
                kind="number",
                default="30",
            ),
            PipelineInputView(
                key="optimize_n_trials",
                label="Optuna trials per combo",
                kind="number",
                default="60",
            ),
            PipelineInputView(
                key="exchange",
                label="Exchange",
                kind="text",
                default="hyperliquid",
            ),
        ),
        full=True,
    ),
    PipelineSpec(
        id="wondertrader-platform",
        title="WonderTrader (backtest + live readiness)",
        description=(
            "Smoke-test dist configs and sample IF data → optional WtBtRunner experiment "
            "(CTA/HFT/UFT/exec) → live template checklist (WtRunnerCta/Hft/Uft)."
        ),
        fn=pipeline_wondertrader_platform,
        steps=_steps(
            ("smoke", "Dist layout + English operator files"),
            ("live_check", "WtRunner config templates"),
            ("backtest", "Four-engine WtBtRunner experiment"),
        ),
        inputs=(
            PipelineInputView(
                key="full_backtest",
                label="Run WtBtRunner experiment",
                kind="boolean",
                default="true",
            ),
            PipelineInputView(
                key="build_runner",
                label="Build macos_bt first",
                kind="boolean",
                default="false",
                hint="macOS only; cmake + make WtBtRunner",
            ),
        ),
        full=True,
    ),
)


def pipeline_spec_to_api(spec: PipelineSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "title": spec.title,
        "description": spec.description,
        "full": spec.full,
        "steps": [{"id": step.id, "title": step.title} for step in spec.steps],
        "inputs": [
            {
                "key": field.key,
                "label": field.label,
                "kind": field.kind,
                "required": field.required,
                "default": field.default,
                "hint": field.hint,
                "options": [{"value": choice.value, "label": choice.label} for choice in field.options],
            }
            for field in spec.inputs
        ],
    }


def list_pipelines() -> list[PipelineSpec]:
    return list(PIPELINES)


def get_pipeline(pipeline_id: str) -> PipelineSpec:
    for spec in PIPELINES:
        if spec.id == pipeline_id:
            return spec
    raise KeyError(f"unknown pipeline: {pipeline_id}")


def run_pipeline(pipeline_id: str, **kwargs: Any) -> PipelineResult:
    return get_pipeline(pipeline_id).fn(**kwargs)
