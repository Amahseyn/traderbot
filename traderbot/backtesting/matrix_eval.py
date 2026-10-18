from __future__ import annotations

import itertools
import json
import random
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from traderbot.algorithms.cli_args import default_strategy_namespace, merge_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, pair_algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.strategy_exchanges import exchanges_for_strategy, strategy_supported_on
from traderbot.algorithms.strategies.funding_carry import FundingCarryAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.eval_data import EVAL_RESOLUTIONS, fetch_history_bars, nobitex_symbol
from traderbot.backtesting.funding_carry_engine import run_funding_carry_backtest
from traderbot.backtesting.oos_metrics import aggregate_sample_metrics, summarize_pair_run, summarize_single_asset_run
from traderbot.backtesting.pair_engine import run_pair_backtest_for_exchange
from traderbot.backtesting.robust_defaults import DEFAULT_TUNE_GRIDS
from traderbot.hyperliquid.funding import fetch_hyperliquid_funding_history
from traderbot.markets.execution_costs import execution_cost_profile
from traderbot.markets.exchange import normalize_live_exchange

SAMPLE_COUNT_DEFAULT = 100
MIN_TRADES_TRAIN = 2
MIN_WINDOW_BARS = 120
MAX_PARAM_COMBOS = 12
SAMPLE_WORKERS = 8

PAIR_PARAM_GRID: dict[str, list[Any]] = {
    "lookback_period": [40, 60, 90],
    "entry_threshold": [1.5, 2.0, 2.5],
    "exit_threshold": [0.35, 0.5],
}

GRID_PARAM_GRID: dict[str, list[Any]] = {
    "grid_count": [4, 6, 8],
    "take_profit_pct": [0.008, 0.012, 0.018],
}

FUNDING_PARAM_GRID: dict[str, list[Any]] = {
    "entry_funding_rate": [0.00003, 0.00005, 0.00008],
    "exit_funding_rate": [0.00001, 0.00002],
    "position_fraction": [0.35, 0.5],
}

MM_PARAM_GRID: dict[str, list[Any]] = {
    "half_spread_pct": [0.0003, 0.0005, 0.0008],
}

NOBITEX_MARKETS: tuple[tuple[str, str, str], ...] = (
    ("btc", "irt", "BTCIRT"),
    ("eth", "irt", "ETHIRT"),
    ("btc", "usdt", "BTCUSDT"),
    ("eth", "usdt", "ETHUSDT"),
)

HYPERLIQUID_MARKETS: tuple[str, ...] = ("btc", "eth", "sol", "arb")


@dataclass
class MatrixEvalConfig:
    sample_count: int = SAMPLE_COUNT_DEFAULT
    months: int = 6
    seed: int = 42
    out_dir: Path = Path("results/strategy_eval")
    use_cache: bool = True


def _param_combos(grid: dict[str, list[Any]], *, max_combos: int = MAX_PARAM_COMBOS) -> list[dict[str, Any]]:
    keys = list(grid.keys())
    if not keys:
        return [{}]
    product = list(itertools.product(*(grid[key] for key in keys)))
    if len(product) > max_combos:
        random.shuffle(product)
        product = product[:max_combos]
    return [{keys[index]: values[index] for index in range(len(keys))} for values in product]


def _split_train_test(bars: list[dict[str, Any]], train_fraction: float = 0.6) -> tuple[list, list]:
    if len(bars) < MIN_WINDOW_BARS:
        return [], []
    train_end = max(MIN_WINDOW_BARS // 2, int(len(bars) * train_fraction))
    if train_end >= len(bars) - 30:
        train_end = len(bars) - 30
    if train_end < 40:
        return [], []
    return bars[:train_end], bars[train_end:]


def _random_window(
    bars: list[dict[str, Any]],
    rng: random.Random,
    *,
    min_fraction: float = 0.25,
    max_fraction: float = 0.55,
) -> list[dict[str, Any]]:
    if len(bars) < MIN_WINDOW_BARS:
        return []
    max_len = max(MIN_WINDOW_BARS, int(len(bars) * max_fraction))
    min_len = max(MIN_WINDOW_BARS, int(len(bars) * min_fraction))
    window_len = rng.randint(min_len, max_len)
    start = rng.randint(0, len(bars) - window_len)
    return bars[start : start + window_len]


def _grid_bounds_from_train(train_bars: list[dict[str, Any]]) -> tuple[float, float]:
    from traderbot.algorithms.strategies.spot_grid import grid_price_bounds_from_bars

    return grid_price_bounds_from_bars(train_bars)


def _tune_single_asset(
    strategy_id: str,
    train_bars: list[dict[str, Any]],
    *,
    fee_rate: float,
    slippage_rate: float,
    rng: random.Random,
) -> dict[str, Any]:
    grid = dict(DEFAULT_TUNE_GRIDS.get(strategy_id, {}))
    if strategy_id == "spot_grid":
        grid = dict(GRID_PARAM_GRID)
    elif strategy_id == "perp_market_making":
        grid = dict(MM_PARAM_GRID)
    combos = _param_combos(grid)
    best_params: dict[str, Any] = {}
    best_return = float("-inf")
    namespace = default_strategy_namespace()
    start_price, end_price = _grid_bounds_from_train(train_bars)

    for combo in combos:
        merged = merge_strategy_namespace(namespace)
        for key, value in combo.items():
            setattr(merged, key, value)
        if strategy_id == "spot_grid":
            setattr(merged, "grid_start_price", start_price)
            setattr(merged, "grid_end_price", end_price)
        kwargs = strategy_kwargs_from_namespace(strategy_id, merged)
        try:
            algorithm = algorithm_for_id(strategy_id, **kwargs)
        except ValueError:
            continue
        result = run_backtest(
            algorithm,
            train_bars,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
        )
        if len(result.trades) < MIN_TRADES_TRAIN and strategy_id not in ("spot_grid", "perp_market_making"):
            continue
        if result.return_pct > best_return:
            best_return = result.return_pct
            best_params = dict(combo)
            if strategy_id == "spot_grid":
                best_params["grid_start_price"] = start_price
                best_params["grid_end_price"] = end_price
    if not best_params and strategy_id == "spot_grid":
        best_params = {
            "grid_count": 6,
            "take_profit_pct": 0.012,
            "grid_start_price": start_price,
            "grid_end_price": end_price,
        }
    return best_params


def _run_single_oos(
    strategy_id: str,
    test_bars: list[dict[str, Any]],
    params: dict[str, Any],
    *,
    fee_rate: float,
    slippage_rate: float,
    resolution: str,
) -> dict[str, Any]:
    namespace = default_strategy_namespace()
    merged = merge_strategy_namespace(namespace)
    for key, value in params.items():
        setattr(merged, key, value)
    kwargs = strategy_kwargs_from_namespace(strategy_id, merged)
    algorithm = algorithm_for_id(strategy_id, **kwargs)
    result = run_backtest(
        algorithm,
        test_bars,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )
    return summarize_single_asset_run(result, test_bars, resolution=resolution, algorithm=algorithm)


def _tune_pair(train_d: list, train_h: list, fee_rate: float, slippage_rate: float, exchange: str) -> dict[str, Any]:
    best: dict[str, Any] = {}
    best_return = float("-inf")
    for combo in _param_combos(PAIR_PARAM_GRID):
        algo = pair_algorithm_for_id("pair_trading", **combo)
        result = run_pair_backtest_for_exchange(
            exchange,
            algo,
            train_d,
            train_h,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
        )
        if result.return_pct > best_return:
            best_return = result.return_pct
            best = dict(combo)
    return best or {"lookback_period": 60, "entry_threshold": 2.0, "exit_threshold": 0.5}


def _run_pair_oos(
    test_d: list,
    test_h: list,
    params: dict[str, Any],
    *,
    exchange: str,
    fee_rate: float,
    slippage_rate: float,
    resolution: str,
) -> dict[str, Any]:
    algo = pair_algorithm_for_id("pair_trading", **params)
    result = run_pair_backtest_for_exchange(
        exchange,
        algo,
        test_d,
        test_h,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )
    return summarize_pair_run(result, test_d, resolution=resolution)


def _tune_funding(train_bars: list, funding_events: list, fee_rate: float, slippage_rate: float) -> dict[str, Any]:
    train_start = int(train_bars[0]["timestamp"])
    train_end = int(train_bars[-1]["timestamp"])
    train_funding = [row for row in funding_events if train_start <= row["time_unix_seconds"] <= train_end]
    if not train_funding:
        return {"entry_funding_rate": 0.00005, "exit_funding_rate": 0.00002, "position_fraction": 0.5}
    best: dict[str, Any] = {}
    best_return = float("-inf")
    for combo in _param_combos(FUNDING_PARAM_GRID):
        algo = FundingCarryAlgorithm(**combo)
        result = run_funding_carry_backtest(algo, train_bars, train_funding, fee_rate=fee_rate, slippage_rate=slippage_rate)
        if result.return_pct > best_return:
            best_return = result.return_pct
            best = dict(combo)
    return best or {"entry_funding_rate": 0.00005, "exit_funding_rate": 0.00002, "position_fraction": 0.5}


def _run_funding_oos(
    test_bars: list,
    funding_events: list,
    params: dict[str, Any],
    *,
    fee_rate: float,
    slippage_rate: float,
) -> dict[str, Any]:
    test_start = int(test_bars[0]["timestamp"])
    test_end = int(test_bars[-1]["timestamp"])
    test_funding = [row for row in funding_events if test_start <= row["time_unix_seconds"] <= test_end]
    algo = FundingCarryAlgorithm(**params)
    result = run_funding_carry_backtest(algo, test_bars, test_funding, fee_rate=fee_rate, slippage_rate=slippage_rate)
    from traderbot.backtesting.metrics import buy_and_hold_return_pct

    bench = buy_and_hold_return_pct(test_bars, fee_rate=fee_rate, slippage_rate=slippage_rate)
    return {
        "return_pct": round(result.return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "trade_count": result.trade_count,
        "total_fees": round(result.total_fees, 4),
        "buy_and_hold_return_pct": round(bench, 4),
        "excess_vs_buy_hold_pct": round(result.return_pct - bench, 4),
        "sharpe_ratio": 0.0,
    }


def evaluate_single_asset_cell(
    *,
    exchange: str,
    strategy_id: str,
    symbol_key: str,
    resolution: str,
    bars: list[dict[str, Any]],
    config: MatrixEvalConfig,
    rng: random.Random,
) -> list[dict[str, Any]]:
    costs = execution_cost_profile(exchange, fee_role="taker")

    def one_sample(_index: int) -> dict[str, Any] | None:
        sample_rng = random.Random(rng.randint(0, 2**31 - 1))
        window = _random_window(bars, sample_rng)
        train, test = _split_train_test(window)
        if not train or not test:
            return None
        params = _tune_single_asset(
            strategy_id,
            train,
            fee_rate=costs.fee_rate,
            slippage_rate=costs.slippage_rate,
            rng=sample_rng,
        )
        if not params and strategy_id not in ("spot_grid",):
            return None
        try:
            metrics = _run_single_oos(
                strategy_id,
                test,
                params,
                fee_rate=costs.fee_rate,
                slippage_rate=costs.slippage_rate,
                resolution=resolution,
            )
            metrics["params"] = params
            return metrics
        except ValueError:
            return None

    samples: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=SAMPLE_WORKERS) as pool:
        futures = [pool.submit(one_sample, index) for index in range(config.sample_count)]
        for future in as_completed(futures):
            row = future.result()
            if row is not None:
                samples.append(row)
    return samples


def evaluate_pair_cell(
    *,
    exchange: str,
    resolution: str,
    bars_d: list,
    bars_h: list,
    config: MatrixEvalConfig,
    rng: random.Random,
) -> list[dict[str, Any]]:
    from traderbot.algorithms.pair_trading.spread import align_bars_by_timestamp

    aligned = align_bars_by_timestamp(bars_d, bars_h)
    if len(aligned) < MIN_WINDOW_BARS:
        return []
    costs = execution_cost_profile(exchange, fee_role="taker")
    def one_sample(_index: int) -> dict[str, Any] | None:
        sample_rng = random.Random(rng.randint(0, 2**31 - 1))
        window = _random_window(aligned, sample_rng)
        train, test = _split_train_test(window)
        if not train or not test:
            return None
        train_d = [dict(bar) for bar in train]
        train_h = [dict(bar, close=bar["hedge_close"]) for bar in train]
        test_d = [dict(bar) for bar in test]
        test_h = [dict(bar, close=bar["hedge_close"]) for bar in test]
        params = _tune_pair(train_d, train_h, costs.fee_rate, costs.slippage_rate, exchange)
        metrics = _run_pair_oos(
            test_d,
            test_h,
            params,
            exchange=exchange,
            fee_rate=costs.fee_rate,
            slippage_rate=costs.slippage_rate,
            resolution=resolution,
        )
        metrics["params"] = params
        return metrics

    samples: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=SAMPLE_WORKERS) as pool:
        futures = [pool.submit(one_sample, index) for index in range(config.sample_count)]
        for future in as_completed(futures):
            row = future.result()
            if row is not None:
                samples.append(row)
    return samples


def evaluate_funding_cell(
    *,
    src: str,
    resolution: str,
    bars: list,
    funding_events: list,
    config: MatrixEvalConfig,
    rng: random.Random,
) -> list[dict[str, Any]]:
    costs = execution_cost_profile("hyperliquid", fee_role="taker")
    def one_sample(_index: int) -> dict[str, Any] | None:
        sample_rng = random.Random(rng.randint(0, 2**31 - 1))
        window = _random_window(bars, sample_rng)
        train, test = _split_train_test(window)
        if not train or not test:
            return None
        test_start = int(test[0]["timestamp"])
        test_end = int(test[-1]["timestamp"])
        test_funding = [row for row in funding_events if test_start <= row["time_unix_seconds"] <= test_end]
        if not test_funding:
            return None
        params = _tune_funding(train, funding_events, costs.fee_rate, costs.slippage_rate)
        metrics = _run_funding_oos(test, funding_events, params, fee_rate=costs.fee_rate, slippage_rate=costs.slippage_rate)
        metrics["params"] = params
        return metrics

    samples: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=SAMPLE_WORKERS) as pool:
        futures = [pool.submit(one_sample, index) for index in range(config.sample_count)]
        for future in as_completed(futures):
            row = future.result()
            if row is not None:
                samples.append(row)
    return samples


def _cell_key(exchange: str, market: str, resolution: str, strategy_id: str) -> str:
    return f"{exchange}:{market}:{resolution}:{strategy_id}"


def _pick_selector_candidate(cell_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Best robust strategy for one market/resolution across strategies evaluated."""
    candidates: list[tuple[str, dict[str, Any]]] = []
    for strategy_id, aggregate in cell_results.items():
        if aggregate.get("sample_count", 0) < 20:
            continue
        median_return = aggregate.get("median_return_pct", 0.0)
        median_excess = aggregate.get("median_excess_vs_buy_hold_pct", 0.0)
        pct_profitable = aggregate.get("pct_profitable_windows", 0.0)
        if pct_profitable >= 52.0 and median_excess > 0.0:
            candidates.append((strategy_id, aggregate))
    if not candidates:
        return {"recommended": False, "reason": "No strategy met OOS robustness thresholds."}
    candidates.sort(key=lambda item: (item[1].get("median_excess_vs_buy_hold_pct", 0), item[1].get("median_sharpe", 0)), reverse=True)
    winner_id, winner_stats = candidates[0]
    return {
        "recommended": True,
        "strategy_id": winner_id,
        "median_return_pct": winner_stats.get("median_return_pct"),
        "median_excess_vs_buy_hold_pct": winner_stats.get("median_excess_vs_buy_hold_pct"),
        "pct_profitable_windows": winner_stats.get("pct_profitable_windows"),
        "median_sharpe": winner_stats.get("median_sharpe"),
    }


def run_full_matrix_evaluation(config: MatrixEvalConfig, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    from traderbot.algorithms.registry import backtest_strategy_ids

    rng = random.Random(config.seed)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    log = progress or (lambda _message: None)

    all_results: dict[str, Any] = {
        "config": {
            "sample_count": config.sample_count,
            "months": config.months,
            "seed": config.seed,
            "resolutions": list(EVAL_RESOLUTIONS),
        },
        "cells": {},
    }
    selector: dict[str, Any] = {}

    single_strategies = [sid for sid in backtest_strategy_ids()]

    for exchange in ("nobitex", "hyperliquid"):
        if exchange == "nobitex":
            market_rows = [(src, dst, sym) for src, dst, sym in NOBITEX_MARKETS]
        else:
            market_rows = [(src, "usdt", src) for src in HYPERLIQUID_MARKETS]
        for _src, dst, symbol_key in market_rows:
            market_label = symbol_key if exchange == "nobitex" else _src.lower()
            fetch_key = symbol_key if exchange == "nobitex" else _src
            for resolution in EVAL_RESOLUTIONS:
                log(f"Loading {exchange} {market_label} {resolution}…")
                bars = fetch_history_bars(
                    exchange=exchange,
                    symbol_key=fetch_key,
                    resolution=resolution,
                    months=config.months,
                    use_cache=config.use_cache,
                )
                if len(bars) < MIN_WINDOW_BARS:
                    log(f"Skip {exchange} {market_label} {resolution}: only {len(bars)} bars")
                    continue

                cell_bucket: dict[str, dict[str, Any]] = {}
                selector_key = f"{exchange}:{market_label}:{resolution}"

                for strategy_id in single_strategies:
                    if not strategy_supported_on(strategy_id, exchange):
                        continue
                    log(f"Eval {strategy_id} {exchange} {market_label} {resolution}")
                    samples = evaluate_single_asset_cell(
                        exchange=exchange,
                        strategy_id=strategy_id,
                        symbol_key=market_label,
                        resolution=resolution,
                        bars=bars,
                        config=config,
                        rng=rng,
                    )
                    aggregate = aggregate_sample_metrics(samples)
                    aggregate["median_excess_vs_buy_hold_pct"] = round(
                        statistics.median([s.get("excess_vs_buy_hold_pct", 0.0) for s in samples]) if samples else 0.0,
                        4,
                    )
                    key = _cell_key(exchange, market_label, resolution, strategy_id)
                    all_results["cells"][key] = {"samples": len(samples), "aggregate": aggregate}
                    cell_bucket[strategy_id] = aggregate
                    (config.out_dir / "matrix_summary.json").write_text(
                        json.dumps(all_results, indent=2),
                        encoding="utf-8",
                    )

                if strategy_supported_on("pair_trading", exchange):
                    hedge_src = "eth" if _src == "btc" else "btc"
                    hedge_key = nobitex_symbol(hedge_src, dst) if exchange == "nobitex" else hedge_src
                    bars_h = fetch_history_bars(
                        exchange=exchange,
                        symbol_key=hedge_key if exchange == "nobitex" else hedge_src,
                        resolution=resolution,
                        months=config.months,
                        use_cache=config.use_cache,
                    )
                    if len(bars_h) >= MIN_WINDOW_BARS:
                        log(f"Eval pair_trading {exchange} {market_label}/{hedge_key} {resolution}")
                        pair_samples = evaluate_pair_cell(
                            exchange=exchange,
                            resolution=resolution,
                            bars_d=bars,
                            bars_h=bars_h,
                            config=config,
                            rng=rng,
                        )
                        aggregate = aggregate_sample_metrics(pair_samples)
                        aggregate["median_excess_vs_buy_hold_pct"] = round(
                            statistics.median([s.get("excess_vs_buy_hold_pct", 0.0) for s in pair_samples])
                            if pair_samples
                            else 0.0,
                            4,
                        )
                        key = _cell_key(exchange, f"{market_label}+{hedge_key}", resolution, "pair_trading")
                        all_results["cells"][key] = {"samples": len(pair_samples), "aggregate": aggregate}
                        cell_bucket["pair_trading"] = aggregate

                if exchange == "hyperliquid" and strategy_supported_on("funding_carry", exchange):
                    try:
                        funding_events = fetch_hyperliquid_funding_history(_src, max_hours=len(bars) * 2)
                    except Exception:  # noqa: BLE001
                        funding_events = []
                    if funding_events:
                        log(f"Eval funding_carry {exchange} {_src} {resolution}")
                        funding_samples = evaluate_funding_cell(
                            src=_src,
                            resolution=resolution,
                            bars=bars,
                            funding_events=funding_events,
                            config=config,
                            rng=rng,
                        )
                        aggregate = aggregate_sample_metrics(funding_samples)
                        aggregate["median_excess_vs_buy_hold_pct"] = round(
                            statistics.median([s.get("excess_vs_buy_hold_pct", 0.0) for s in funding_samples])
                            if funding_samples
                            else 0.0,
                            4,
                        )
                        key = _cell_key(exchange, market_label, resolution, "funding_carry")
                        all_results["cells"][key] = {"samples": len(funding_samples), "aggregate": aggregate}
                        cell_bucket["funding_carry"] = aggregate

                selector[selector_key] = _pick_selector_candidate(cell_bucket)

    summary_path = config.out_dir / "matrix_summary.json"
    summary_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    selector_path = Path("config/strategy_selector.json")
    selector_path.parent.mkdir(parents=True, exist_ok=True)
    selector_path.write_text(json.dumps(selector, indent=2), encoding="utf-8")
    all_results["selector_path"] = str(selector_path)
    return all_results
