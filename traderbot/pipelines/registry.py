from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from traderbot.pipelines.base import PipelineFn, PipelineResult
from traderbot.pipelines.definitions import (
    pipeline_crypto_1h_local,
    pipeline_export_then_hourly,
    pipeline_crypto_jobs_export,
    pipeline_sma_backtest,
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
        description="Export crypto 1h jobs, then compare rule-based strategies on each hourly file. Skips LightGBM.",
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
