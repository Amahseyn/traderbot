from __future__ import annotations

import json
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
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
)


def run_finrl_platform_task(body: dict[str, Any]) -> None:
    from traderbot.integrations.finrl_trading.research import run_full_platform_experiment

    intervals_raw = str(body.get("intervals") or "1,5")
    intervals = [p.strip() for p in intervals_raw.split(",") if p.strip()]

    def log(msg: str) -> None:
        print(msg, flush=True)

    report = run_full_platform_experiment(
        src=str(body.get("src") or "btc"),
        dst=str(body.get("dst") or "usdt"),
        intervals=intervals,
        max_bars=int(body.get("max_bars") or 100),
        equity_periods=int(body.get("equity_periods") or 100),
        include_equity_rotation=bool(body.get("include_equity_rotation", True)),
        include_strategy_compare=bool(body.get("include_strategy_compare", True)),
        include_hyperliquid_algo_sweep=bool(body.get("include_hyperliquid_algo_sweep", False)),
        include_deploy_backtest=bool(body.get("include_deploy_backtest", False)),
        use_optimized_params=bool(body.get("use_optimized_params", True)),
        log=log,
    )
    print(json.dumps(report, indent=2, default=str), flush=True)


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
    jobs = [
        {
            "symbol": symbol,
            "src": str(src),
            "dst": str(dst),
            "exchange": str(fields.get("exchange") or "nobitex"),
            "interval": str(interval),
            "days": days,
            "max_bars": fields.get("max_bars"),
        }
    ]
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
            fee=float(body.get("fee") if body.get("fee") not in (None, "") else DEFAULT_TRADE_FEE_RATE),
            slippage=DEFAULT_SLIPPAGE_RATE,
            execution=str(body.get("execution") or DEFAULT_BACKTEST_EXECUTION),
            vectorbt=bool(body.get("vectorbt")),
            strategy_namespace=_strategy_namespace_from_body(body),
            mode=mode,
            use_optimized_strategy_params=bool(body.get("use_optimized_strategy_params", True)),
        ),
        log=lambda message: print(message, flush=True),
    )


def run_strategy_sweep_task(body: dict[str, Any], csv_path: str) -> None:
    import json

    from lab.sweep_job import run_recorded_strategy_sweep

    payload = run_recorded_strategy_sweep(body, Path(csv_path))
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
            fee=float(body.get("fee") if body.get("fee") not in (None, "") else DEFAULT_TRADE_FEE_RATE),
            slippage=DEFAULT_SLIPPAGE_RATE,
            execution=str(body.get("execution") or DEFAULT_BACKTEST_EXECUTION),
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
        if field.key == "days":
            continue
        if field.kind not in ("select", "number", "text", "boolean"):
            continue
        if field.key not in body or body[field.key] is None:
            if field.kind == "text" and field.default:
                kwargs[field.key] = field.default
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
