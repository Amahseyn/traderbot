from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from traderbot.pipelines.base import PipelineFn, PipelineResult
from traderbot.pipelines.definitions import (
    pipeline_chronos_single,
    pipeline_crypto_1h_local,
    pipeline_full_research,
    pipeline_lightgbm_multisource,
    pipeline_lightgbm_single_asset,
    pipeline_multisource_export,
    pipeline_sma_backtest,
)


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    id: str
    title: str
    description: str
    fn: PipelineFn


PIPELINES: tuple[PipelineSpec, ...] = (
    PipelineSpec(
        id="multisource-export",
        title="Export 5 markets",
        description="Nobitex OHLC → data/crypto (ohlc + per-horizon folders).",
        fn=pipeline_multisource_export,
    ),
    PipelineSpec(
        id="lightgbm-multisource-default",
        title="LightGBM multisource (1h default)",
        description="Batch LightGBM on every multisource CSV; default 1h horizon per file.",
        fn=lambda **kw: pipeline_lightgbm_multisource(all_horizons=False, **kw),
    ),
    PipelineSpec(
        id="lightgbm-multisource-all-horizons",
        title="LightGBM multisource (all horizons)",
        description="Batch LightGBM with every default horizon (1m…1d) per CSV.",
        fn=lambda **kw: pipeline_lightgbm_multisource(all_horizons=True, **kw),
    ),
    PipelineSpec(
        id="lightgbm-single-asset",
        title="LightGBM one CSV",
        description="All default horizons for a single OHLC file.",
        fn=pipeline_lightgbm_single_asset,
    ),
    PipelineSpec(
        id="chronos-single",
        title="Chronos one CSV",
        description="Pretrained Chronos eval + plots (optional chronos extra).",
        fn=pipeline_chronos_single,
    ),
    PipelineSpec(
        id="sma-backtest",
        title="SMA backtest",
        description="Rule-based SMA cross backtest on one CSV.",
        fn=pipeline_sma_backtest,
    ),
    PipelineSpec(
        id="crypto-1h-local",
        title="Crypto 1h local (no export)",
        description="Full on-disk *_60.csv per asset (or --tail-bars); compare all strategies + LightGBM when bar count meets ML minimum.",
        fn=pipeline_crypto_1h_local,
    ),
    PipelineSpec(
        id="full-research-lightgbm",
        title="Full research (export + all horizons)",
        description="Export 5 sources (90d) then LightGBM all horizons + manifests.",
        fn=pipeline_full_research,
    ),
)


def list_pipelines() -> list[PipelineSpec]:
    return list(PIPELINES)


def get_pipeline(pipeline_id: str) -> PipelineSpec:
    for spec in PIPELINES:
        if spec.id == pipeline_id:
            return spec
    raise KeyError(f"unknown pipeline: {pipeline_id}")


def run_pipeline(pipeline_id: str, **kwargs: Any) -> PipelineResult:
    return get_pipeline(pipeline_id).fn(**kwargs)
