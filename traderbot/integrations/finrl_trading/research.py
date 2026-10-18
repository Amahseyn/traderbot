from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from traderbot.data.export import run_export
from traderbot.integrations.finrl_trading.capabilities import capabilities_api_payload
from traderbot.integrations.finrl_trading.compare import compare_finrl_strategies_on_csv
from traderbot.integrations.finrl_trading.env import load_shared_env
from traderbot.integrations.finrl_trading.paths import finrl_trading_root, traderbot_root
from traderbot.integrations.finrl_trading.runners import (
    run_finrl_deploy_adaptive_rotation,
    run_finrl_hyperliquid_research_validate,
)
from traderbot.hyperliquid.market_data import hyperliquid_resolution
from traderbot.markets.market_data import market_symbol

LogFn = Callable[[str], None]


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def export_hyperliquid_for_finrl(
    *,
    src: str,
    dst: str,
    intervals: list[str],
    max_bars: int,
    output_dir: Path,
) -> list[Path]:
    symbol = market_symbol(src, dst)
    days = max(2, (max_bars * 5) // 1440 + 1)
    normalized = [hyperliquid_resolution(i) for i in intervals]
    jobs = [
        {
            "symbol": symbol,
            "src": src.strip().lower(),
            "dst": dst.strip().lower(),
            "interval": interval,
            "days": days,
            "max_bars": max_bars,
            "exchange": "hyperliquid",
        }
        for interval in normalized
    ]
    written = run_export(jobs, days=days, output_dir=output_dir, to_ts=None, crypto_layout=False)
    return list(written)


def run_finrl_intraday_experiment(
    *,
    coin: str,
    intervals: list[str],
    max_bars: int,
    out_dir: Path | None = None,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Run the intraday EMA experiment with traderbot's vendored FinRL core."""
    log = log or _log_default
    from traderbot.finrl.intraday_experiment import run_hyperliquid_intraday_experiment

    resolved_out = out_dir or (traderbot_root() / "data" / "hyperliquid")
    log(f"FinRL intraday (native): {coin.upper()} intervals={intervals} max_bars={max_bars}")
    return run_hyperliquid_intraday_experiment(
        coin=coin.upper(),
        intervals=list(intervals),
        max_bars=max_bars,
        out_dir=resolved_out,
        log=log,
    )


def run_finrl_adaptive_rotation_report(
    *,
    periods: int = 100,
    end_date: str = "2024-12-31",
    skip_backtest: bool = False,
    log: LogFn | None = None,
) -> dict[str, Any]:
    log = log or _log_default
    root = finrl_trading_root()
    script = root / "scripts" / "report_adaptive_rotation_100periods.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    cmd = [
        sys.executable,
        str(script),
        "--periods",
        str(periods),
        "--end",
        end_date,
    ]
    if skip_backtest:
        cmd.append("--skip-backtest")
    log(f"FinRL adaptive rotation: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    log(proc.stdout)
    if proc.returncode != 0:
        log(proc.stderr)
        raise RuntimeError(f"FinRL adaptive rotation report failed (exit {proc.returncode})")
    report_path = root / "data" / f"adaptive_rotation_{periods}periods_report.json"
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    return {"stdout": proc.stdout}


def compare_finrl_ema_on_csvs(
    csv_paths: list[Path],
    *,
    log: LogFn | None = None,
) -> list[dict[str, Any]]:
    from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
    from traderbot.algorithms.cli_args import default_strategy_namespace
    from traderbot.backtesting import load_bars_csv, run_backtest, backtest_summary_dict
    from traderbot.markets.execution_costs import execution_cost_profile

    log = log or _log_default
    costs = execution_cost_profile("hyperliquid", fee_role="taker", market_kind="perp")
    ns = default_strategy_namespace(fast=12, slow=48)
    kwargs = strategy_kwargs_from_namespace("finrl_ema_intraday", ns)
    summaries: list[dict[str, Any]] = []
    for path in csv_paths:
        bars = load_bars_csv(path)
        algo = algorithm_for_id("finrl_ema_intraday", **kwargs)
        result = run_backtest(
            algo,
            bars,
            initial_cash=10_000.0,
            fee_rate=costs.fee_rate,
            slippage_rate=costs.slippage_rate,
            execution="next_open",
        )
        summary = backtest_summary_dict(algo, result, bars=len(bars))
        summary["csv"] = str(path)
        summary["strategy_id"] = "finrl_ema_intraday"
        summaries.append(summary)
        log(f"traderbot backtest {path.name}: return {summary.get('return_pct')}%")
    return summaries


def run_full_platform_experiment(
    *,
    src: str = "btc",
    dst: str = "usdt",
    intervals: list[str] | None = None,
    max_bars: int = 100,
    equity_periods: int = 100,
    include_equity_rotation: bool = True,
    include_strategy_compare: bool = True,
    include_hyperliquid_algo_sweep: bool = False,
    include_deploy_backtest: bool = False,
    use_optimized_params: bool = True,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """
    End-to-end traderbot + FinRL-Trading:
    export → multi-strategy compare (optimized) → FinRL intraday → equity rotation → optional HL sweep.
    """
    log = log or _log_default
    load_shared_env()
    intervals = [hyperliquid_resolution(i) for i in (intervals or ["1", "5"])]
    try:
        finrl_root: Path | None = finrl_trading_root()
    except FileNotFoundError:
        finrl_root = None
    out_dir = traderbot_root() / "data" / "hyperliquid"
    out_dir.mkdir(parents=True, exist_ok=True)

    log("=== [1] Export Hyperliquid OHLC ===")
    csv_files = export_hyperliquid_for_finrl(
        src=src, dst=dst, intervals=intervals, max_bars=max_bars, output_dir=out_dir
    )
    log(f"Exported {len(csv_files)} files")

    strategy_compare: list[dict[str, Any]] = []
    if include_strategy_compare:
        log("=== [2] Compare FinRL-aligned strategies (robust + sweep DB when available) ===")
        for path in csv_files:
            strategy_compare.append(
                compare_finrl_strategies_on_csv(
                    path,
                    use_optimized_params=use_optimized_params,
                    log=log,
                )
            )

    log("=== [3] Traderbot finrl_ema_intraday backtest ===")
    tb_backtests = compare_finrl_ema_on_csvs(csv_files, log=log)

    log("=== [4] FinRL intraday window metrics ===")
    finrl_intraday = run_finrl_intraday_experiment(
        coin=src.upper(), intervals=intervals, max_bars=max_bars, log=log
    )

    equity_report: dict[str, Any] | None = None
    deploy_backtest: dict[str, Any] | None = None
    hl_sweep: dict[str, Any] | None = None

    if include_equity_rotation:
        log("=== [5] FinRL adaptive rotation (100-period report) ===")
        try:
            equity_report = run_finrl_adaptive_rotation_report(
                periods=equity_periods, skip_backtest=False, log=log
            )
        except Exception as exc:
            log(f"adaptive rotation report failed: {exc}")
            equity_report = {"error": str(exc)}

    if include_deploy_backtest:
        log("=== [6] FinRL deploy.sh adaptive_rotation backtest ===")
        try:
            deploy_backtest = run_finrl_deploy_adaptive_rotation(skip_download=True)
        except Exception as exc:
            deploy_backtest = {"error": str(exc)}

    if include_hyperliquid_algo_sweep:
        log("=== [7] Hyperliquid multi-strategy research validate (all algos) ===")
        hl_sweep = run_finrl_hyperliquid_research_validate(
            src=src, intervals=",".join(intervals), max_bars=max_bars
        )

    return {
        "platform": "traderbot+finrl-trading",
        "capabilities": capabilities_api_payload(),
        "traderbot_root": str(traderbot_root()),
        "finrl_trading_root": str(finrl_root) if finrl_root is not None else None,
        "hyperliquid": {"src": src, "dst": dst, "intervals": intervals, "max_bars": max_bars},
        "exported_csv": [str(p) for p in csv_files],
        "strategy_compare": strategy_compare,
        "traderbot_finrl_ema_backtests": tb_backtests,
        "finrl_intraday_report": finrl_intraday,
        "finrl_equity_rotation_report": equity_report,
        "finrl_deploy_backtest": deploy_backtest,
        "hyperliquid_algo_sweep": hl_sweep,
    }
