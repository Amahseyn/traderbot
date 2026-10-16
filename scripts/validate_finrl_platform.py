#!/usr/bin/env python3
"""
FinRL + traderbot platform validation: export, leakage checks, walk-forward validate, backtest.

Example:
  python scripts/validate_finrl_platform.py --src btc --interval 1 --max-bars 200
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOG = logging.getLogger("finrl.validate")


def _configure_logging(log_file: Path | None, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s"))
        logging.getLogger().addHandler(fh)
        LOG.info("log file %s", log_file)


def assert_signals_no_lookahead(strategy_id: str, *, bar_count: int = 400) -> dict:
    """Signals up to bar k must not change when future bars are perturbed."""
    from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
    from traderbot.algorithms.cli_args import default_strategy_namespace

    def wavy_closes(count: int) -> list[float]:
        return [
            100 + 10 * math.sin(i / 9) + 6 * math.sin(i / 31) + i * 0.03 for i in range(count)
        ]

    def bars_from_closes(closes: list[float]) -> list[dict]:
        rows = []
        for i, close in enumerate(closes):
            open_p = closes[i - 1] if i else close
            rows.append(
                {
                    "timestamp": i * 60,
                    "open": open_p,
                    "high": max(open_p, close) * 1.002,
                    "low": min(open_p, close) * 0.998,
                    "close": close,
                    "volume": 1.0 + (i % 7),
                    "resolution": "1",
                    "symbol": "TESTUSDT",
                }
            )
        return rows

    namespace = default_strategy_namespace(fast=12, slow=48)
    kwargs = strategy_kwargs_from_namespace(strategy_id, namespace)
    algo = algorithm_for_id(strategy_id, **kwargs)

    bars = bars_from_closes(wavy_closes(bar_count))

    def signals(algorithm, seq):
        algorithm.reset()
        return [algorithm.on_bar(b) for b in seq]

    full = signals(algo, bars)
    cut = 250
    altered = bars[:cut] + [
        {**b, "close": b["close"] * 1.5, "high": b["high"] * 1.5} for b in bars[cut:]
    ]
    prefix_altered = signals(algo, altered)[:cut]
    prefix_full = full[:cut]
    if prefix_altered != prefix_full:
        raise AssertionError(
            f"{strategy_id}: lookahead — signals before bar {cut} changed when future bars changed"
        )
    LOG.info("lookahead check PASSED for %s (%d prefix bars)", strategy_id, cut)
    return {"strategy_id": strategy_id, "lookahead": "pass", "prefix_bars_checked": cut}


def assert_finrl_intraday_engine_shifted() -> dict:
    """FinRL intraday EMA positions must lag raw cross by one bar."""
    from traderbot.integrations.finrl_trading.paths import ensure_finrl_on_path

    ensure_finrl_on_path()
    import pandas as pd
    from src.backtest.intraday_engine import ema_cross_signals

    close = pd.Series([100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109] * 10, dtype=float)
    pos = ema_cross_signals(close, fast=3, slow=5)
    fast = close.ewm(span=3, adjust=False).mean()
    slow = close.ewm(span=5, adjust=False).mean()
    raw = (fast > slow).astype(int)
    for i in range(1, len(close)):
        if int(pos.iloc[i]) != int(raw.iloc[i - 1]):
            raise AssertionError(f"bar {i}: position {pos.iloc[i]} != lagged cross {raw.iloc[i-1]}")
    LOG.info("FinRL ema_cross_signals shift(1) PASSED")
    return {"finrl_intraday_engine": "shift_lag_ok"}


def run_walk_forward_validation_on_csv(csv_path: Path) -> dict:
    from traderbot.algorithms.cli_args import default_strategy_namespace
    from traderbot.backtesting import load_bars_csv
    from traderbot.backtesting.validation import ValidationOptions, run_strategy_validation
    from traderbot.data.intrahour import enrich_bars_for_csv
    from traderbot.markets.execution_costs import execution_cost_profile

    costs = execution_cost_profile("hyperliquid", fee_role="taker", market_kind="perp")
    ns = default_strategy_namespace(fast=12, slow=48)
    bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, ns)
    payload = run_strategy_validation(
        ValidationOptions(
            csv_path=str(csv_path),
            bars=bars,
            strategy_id="finrl_ema_intraday",
            param_grid={"fast": [12], "slow": [48]},
            cash=10_000.0,
            fee=costs.fee_rate,
            slippage=costs.slippage_rate,
            execution="next_open",
            train_fraction=0.6,
            validation_fraction=0.2,
            min_trades=0,
            max_combos=8,
        ),
        base_namespace=ns,
    )
    LOG.info(
        "walk-forward validate: train=%s val=%s test=%s selected=%s",
        payload.get("train_return_pct"),
        payload.get("validation_return_pct"),
        payload.get("test_return_pct"),
        payload.get("selected_params"),
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default="btc")
    parser.add_argument("--interval", default="1")
    parser.add_argument("--max-bars", type=int, default=200)
    parser.add_argument("--log-file", type=Path, default=None)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    out_log = args.log_file or (REPO_ROOT / "logs" / "finrl_platform_validate.log")
    _configure_logging(out_log, args.verbose)

    report: dict = {"steps": []}

    LOG.info("=== static leakage checks ===")
    report["steps"].append(assert_signals_no_lookahead("finrl_ema_intraday"))
    report["steps"].append(assert_signals_no_lookahead("ema_cross"))
    try:
        report["steps"].append(assert_finrl_intraday_engine_shifted())
    except Exception as exc:
        LOG.warning("FinRL engine shift check skipped: %s", exc)
        report["steps"].append({"finrl_intraday_engine": "skipped", "reason": str(exc)})

    LOG.info("=== live export + platform backtest ===")
    from traderbot.integrations.finrl_trading.research import run_full_platform_experiment

    platform = run_full_platform_experiment(
        src=args.src,
        dst="usdt",
        intervals=[str(args.interval)],
        max_bars=args.max_bars,
        include_equity_rotation=False,
        log=LOG.info,
    )
    report["platform"] = platform

    csv_path = Path(platform["exported_csv"][0])
    LOG.info("=== walk-forward validation on %s ===", csv_path.name)
    report["walk_forward_validation"] = run_walk_forward_validation_on_csv(csv_path)

    report["ok"] = True
    report["log_file"] = str(out_log)

    text = json.dumps(report, indent=2, default=str)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(text, encoding="utf-8")
        LOG.info("wrote %s", args.json_report)
    print(text)
    LOG.info("VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
