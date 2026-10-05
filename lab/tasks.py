from __future__ import annotations

from pathlib import Path
from typing import Any

from traderbot.backtesting.compare_session import (
    StrategyCompareOptions,
    StrategyTestOptions,
    run_strategy_compare,
    run_strategy_test,
)
from traderbot.data.export import run_export
from traderbot.markets.market_data import market_symbol


def run_export_task(fields: dict[str, Any]) -> None:
    src = fields.get("src")
    dst = fields.get("dst")
    interval = fields.get("interval")
    if not src or not dst or not interval:
        raise ValueError("export requires src, dst, and interval")
    symbol = market_symbol(str(src), str(dst))
    days = int(fields.get("days") or 30)
    output_dir = Path(str(fields.get("out") or "data"))
    crypto_layout = bool(fields.get("crypto_layout"))
    jobs = [{"symbol": symbol, "interval": str(interval), "days": days}]
    run_export(
        jobs,
        days=days,
        output_dir=output_dir,
        to_ts=None,
        crypto_layout=crypto_layout,
    )


def _strategy_namespace_from_body(body: dict[str, Any]) -> Any:
    from traderbot.algorithms.cli_args import default_strategy_namespace

    return default_strategy_namespace(
        fast=int(body.get("fast") or 5),
        slow=int(body.get("slow") or 20),
        signal=int(body.get("signal") or 9),
        period=int(body.get("period") or 14),
        oversold=float(body.get("oversold") or 30.0),
        overbought=float(body.get("overbought") or 70.0),
        num_std=float(body.get("num_std") or 2.0),
        context_bars=int(body.get("context_bars") or 0),
        price_confirm=bool(body.get("price_confirm")),
        lookback_bars=int(body.get("lookback_bars") or 20),
        atr_period=int(body.get("atr_period") or 14),
        atr_multiplier=float(body.get("atr_multiplier") or 1.5),
        swing_window_bars=int(body.get("swing_window_bars") or 3),
        min_swing_separation_bars=int(body.get("min_swing_separation_bars") or 4),
        pattern_tolerance_ratio=float(body.get("pattern_tolerance_ratio") or 0.02),
        pattern_score_threshold=float(body.get("pattern_score_threshold") or 0.35),
    )


def run_strategy_compare_task(body: dict[str, Any], csv_path: str) -> None:
    csv = Path(csv_path)
    out = body.get("out")
    mode = str(body.get("mode") or "strategies")
    print(f"compare: preparing {csv.name} ({mode}) …", flush=True)
    run_strategy_compare(
        StrategyCompareOptions(
            csv_path=csv,
            out_dir=Path(str(out)) if out else None,
            visualize=bool(body.get("visualize", True)),
            cash=float(body.get("cash") or 10_000.0),
            fee=float(body.get("fee") or 0.0),
            vectorbt=bool(body.get("vectorbt")),
            strategy_namespace=_strategy_namespace_from_body(body),
            mode=mode,
        ),
        log=lambda message: print(message, flush=True),
    )


def run_strategy_test_task(body: dict[str, Any], csv_path: str) -> None:
    csv = Path(csv_path)
    out = body.get("out")
    mode = str(body.get("mode") or "strategies")
    strategy_id = str(body.get("strategy_id") or "")
    print(f"strategy test: preparing {strategy_id} on {csv.name} ({mode}) …", flush=True)
    run_strategy_test(
        StrategyTestOptions(
            csv_path=csv,
            strategy_id=strategy_id,
            out_dir=Path(str(out)) if out else None,
            visualize=bool(body.get("visualize", True)),
            cash=float(body.get("cash") or 10_000.0),
            fee=float(body.get("fee") or 0.0),
            vectorbt=bool(body.get("vectorbt")),
            strategy_namespace=_strategy_namespace_from_body(body),
            mode=mode,
        ),
        log=lambda message: print(message, flush=True),
    )


def run_pipeline_config_task(
    config_path: str,
    *,
    param_overrides: dict[str, Any] | None = None,
    step_param_overrides: dict[str, Any] | None = None,
) -> None:
    from traderbot.pipelines.experiment_config import run_experiment_config

    import json

    payload = run_experiment_config(
        Path(config_path),
        param_overrides=param_overrides,
        step_param_overrides=step_param_overrides,
    )
    print(json.dumps(payload, indent=2))


def run_custom_research_task(body: dict[str, Any]) -> None:
    from lab.custom_research import run_custom_research

    run_custom_research(body)


def run_named_pipeline_task(body: dict[str, Any]) -> None:
    import json

    from traderbot.pipelines.registry import get_pipeline, run_pipeline

    pipeline_id = str(body["pipeline_id"])
    spec = get_pipeline(pipeline_id)
    kwargs: dict[str, Any] = {}
    if body.get("csv"):
        kwargs["csv_path"] = Path(str(body["csv"]))
    if spec.days_kw and body.get("days") is not None:
        kwargs[spec.days_kw] = int(body["days"])
    for field in spec.inputs:
        if field.kind not in ("select", "number") or field.key == "days":
            continue
        if field.key not in body or body[field.key] is None:
            continue
        kwargs[field.key] = body[field.key]
    if "all_assets" in body:
        kwargs["all_assets"] = bool(body["all_assets"])
        if kwargs["all_assets"]:
            kwargs.pop("csv_path", None)
    result = run_pipeline(pipeline_id, **kwargs)
    print(
        json.dumps(
            {
                "pipeline_id": result.pipeline_id,
                "steps": [step.__dict__ for step in result.steps],
                "outputs": result.outputs,
            },
            indent=2,
            default=str,
        ),
    )
