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

    defaults = default_strategy_namespace()
    overrides: dict[str, Any] = {}
    for key, default in vars(defaults).items():
        if key not in body or body[key] in (None, ""):
            continue
        raw = body[key]
        try:
            if isinstance(default, bool):
                overrides[key] = raw if isinstance(raw, bool) else str(raw).lower() not in ("0", "false", "no", "off", "")
            elif isinstance(default, int) and not isinstance(raw, bool):
                overrides[key] = int(raw)
            elif isinstance(default, float) and not isinstance(raw, bool):
                overrides[key] = float(raw)
            else:
                overrides[key] = raw
        except (TypeError, ValueError):
            overrides[key] = raw
    return default_strategy_namespace(**overrides)


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
            slippage=float(body.get("slippage") or 0.0),
            execution=str(body.get("execution") or "close"),
            vectorbt=bool(body.get("vectorbt")),
            strategy_namespace=_strategy_namespace_from_body(body),
            mode=mode,
        ),
        log=lambda message: print(message, flush=True),
    )


def run_strategy_sweep_task(body: dict[str, Any], csv_path: str) -> None:
    import json

    from traderbot.backtesting.sweep import SweepOptions, run_strategy_sweep

    csv = Path(csv_path)
    strategy_id = str(body.get("strategy_id") or "")
    param_grid = {name: list(values) for name, values in dict(body.get("param_grid") or {}).items()}
    holdout_raw = body.get("holdout_tail_bars")
    print(f"sweep: preparing {strategy_id} on {csv.name} ({len(param_grid)} params) …", flush=True)
    payload = run_strategy_sweep(
        SweepOptions(
            csv_path=csv,
            strategy_id=strategy_id,
            param_grid=param_grid,
            cash=float(body.get("cash") or 10_000.0),
            fee=float(body.get("fee") or 0.0),
            slippage=float(body.get("slippage") or 0.0),
            execution=str(body.get("execution") or "close"),
            holdout_tail_bars=None if holdout_raw in (None, "") else int(holdout_raw),
            min_trades=int(body.get("min_trades") or 0),
            max_combos=int(body.get("max_combos") or 64),
        ),
        base_namespace=_strategy_namespace_from_body(body),
    )
    out = body.get("out")
    out_dir = Path(str(out)) if out else Path("results") / "strategies" / "sweep" / f"{csv.stem}_{strategy_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "sweep_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["manifest"] = str(manifest_path)
    from traderbot.recording import try_record

    try_record(
        "sweep_session",
        sweep_payload=payload,
        manifest_path=manifest_path,
    )
    print(json.dumps(payload, indent=2))


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
            slippage=float(body.get("slippage") or 0.0),
            execution=str(body.get("execution") or "close"),
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
