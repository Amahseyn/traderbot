"""Rolling walk-forward evaluation: tune on a window, trade the next unseen window, repeat.

Only out-of-sample (test) segments are aggregated, so the reported edge is what the
parameter-selection procedure would have earned, not the best in-sample fit.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from traderbot.algorithms.cli_args import merge_strategy_namespace
from traderbot.algorithms.pair_trading.spread import align_bars_by_timestamp
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.engine import run_backtest
from traderbot.backtesting.metrics import annualized_sharpe_ratio, return_pct_excluding_warmup
from traderbot.backtesting.pair_engine import run_perp_pair_backtest
from traderbot.backtesting.param_bounds import param_value_error
from traderbot.backtesting.sweep import sweep_rank_key
from traderbot.backtesting.trade_stats import DEFAULT_MIN_TRADES, round_trip_returns, trade_stats
from traderbot.utils.bars import normalize_bar
from traderbot.utils.trading_costs import ResolvesCostRates


@dataclass
class WalkForwardOptions(ResolvesCostRates):
    strategy_id: str
    param_grid: dict[str, list[Any]]
    bars: list[dict[str, Any]] = field(default_factory=list)
    train_bars: int = 2000
    test_bars: int = 500
    warmup_bars: int = 200
    purge_bars: int = 0
    window_mode: Literal["rolling", "expanding"] = "rolling"
    cash: float = 10_000.0
    fee: float | None = None
    slippage: float | None = None
    exchange: str | None = None
    execution: str = "next_open"
    min_trades: int = DEFAULT_MIN_TRADES
    rank_by: str = "edge"
    max_combos: int = 256


@dataclass
class PairWalkForwardOptions(ResolvesCostRates):
    param_grid: dict[str, list[Any]]
    dominant_bars: list[dict[str, Any]] = field(default_factory=list)
    hedge_bars: list[dict[str, Any]] = field(default_factory=list)
    algorithm_factory: Callable[..., PairTradingAlgorithm] | None = None
    train_bars: int = 1000
    test_bars: int = 250
    warmup_bars: int = 50
    purge_bars: int = 0
    window_mode: Literal["rolling", "expanding"] = "rolling"
    cash: float = 10_000.0
    fee: float | None = None
    slippage: float | None = None
    exchange: str | None = None
    execution: str = "next_open"
    rank_by: str = "return_pct"
    max_combos: int = 256


def _combos(grid: dict[str, list[Any]], max_combos: int) -> list[dict[str, Any]]:
    names = list(grid)
    for name in names:
        for value in grid[name]:
            error = param_value_error(name, value)
            if error:
                raise ValueError(error)
    combos = [dict(zip(names, values)) for values in itertools.product(*(grid[n] for n in names))]
    if len(combos) > max_combos:
        raise ValueError(f"walk-forward grid has {len(combos)} combos; max is {max_combos}")
    return combos or [{}]


def _run(options: WalkForwardOptions, base: Any, params: dict[str, Any], bars: list[dict[str, Any]]):
    namespace = merge_strategy_namespace(base)
    for key, value in params.items():
        setattr(namespace, key, value)
    algo = algorithm_for_id(options.strategy_id, **strategy_kwargs_from_namespace(options.strategy_id, namespace))
    return run_backtest(
        algo, bars, initial_cash=options.cash, fee_rate=options.fee, slippage_rate=options.slippage,
        execution=options.execution,
    )


def _oos_segment(result: Any, warmup: int) -> tuple[float, list[float]]:
    """Return OOS % and round-trip returns after the warmup prefix.

    Trades opened during warmup are excluded from the round-trip list.  The
    segment return is the compounded product of the OOS round-trip returns so
    that unrealised PnL from positions entered on in-sample (warmup) data does
    not leak into the out-of-sample equity performance.  When no round trips
    close inside the OOS window, the segment return is 0% (no OOS-initiated
    edge), which is the conservative, leakage-free report.
    """
    curve = result.equity_curve
    if len(curve) <= warmup:
        return 0.0, []
    start_ts = curve[warmup - 1][0] if warmup > 0 else curve[0][0] - 1
    trades = [t for t in result.trades if t.timestamp > start_ts]
    subset = type("R", (), {"trades": trades, "initial_cash": curve[warmup - 1][1] if warmup > 0 else result.initial_cash})()
    oos_returns = round_trip_returns(subset)
    # Segment return = compounded product of OOS round-trip returns.  This
    # excludes carried-in positions whose entry was decided on warmup data.
    compounded = 1.0
    for r in oos_returns:
        compounded *= 1.0 + r
    segment_return = (compounded - 1.0) * 100.0
    return segment_return, oos_returns


def run_walk_forward(options: WalkForwardOptions, base_namespace: Any | None = None) -> dict[str, Any]:
    bars = list(options.bars)
    if options.train_bars < 50 or options.test_bars < 10:
        raise ValueError("train_bars must be >= 50 and test_bars >= 10")
    if len(bars) < options.train_bars + options.test_bars:
        raise ValueError(f"need at least {options.train_bars + options.test_bars} bars, got {len(bars)}")
    combos = _combos(options.param_grid, options.max_combos)
    folds: list[dict[str, Any]] = []
    oos_returns: list[float] = []
    compounded = 1.0
    step = 0
    while True:
        if options.window_mode == "expanding":
            train_start = 0
            train_end = options.train_bars + step * options.test_bars
        else:
            train_start = step * options.test_bars
            train_end = train_start + options.train_bars

        test_start = train_end + options.purge_bars
        test_end = test_start + options.test_bars
        if test_end > len(bars):
            break

        train = bars[train_start:train_end]
        warmup = min(options.warmup_bars, train_end - train_start)
        test = bars[test_start - warmup : test_end]
        rows = []
        for params in combos:
            try:
                result = _run(options, base_namespace, params, train)
            except ValueError:
                continue
            stats = trade_stats(result)
            rows.append({
                "params": params,
                "return_pct": result.return_pct,
                "trades": len(result.trades),
                "eligible": len(result.trades) >= options.min_trades,
                **stats,
            })
        if not rows:
            raise ValueError("walk-forward: no valid parameter combination")
        rows.sort(key=lambda row: sweep_rank_key(row, rank_by=options.rank_by), reverse=True)
        best = rows[0]
        test_result = _run(options, base_namespace, best["params"], test)
        segment_return, segment_trades = _oos_segment(test_result, warmup)
        compounded *= 1.0 + segment_return / 100.0
        oos_returns.extend(segment_trades)
        folds.append({
            "fold_index": step,
            "train_start": int(train[0]["timestamp"]),
            "train_end": int(train[-1]["timestamp"]),
            "train_bars": train_end - train_start,
            "test_start": int(bars[test_start]["timestamp"]),
            "test_end": int(bars[test_end - 1]["timestamp"]),
            "params": best["params"],
            "train_eligible": best["eligible"],
            "train_avg_trade_net_pct": best.get("avg_trade_net_pct"),
            "train_t_stat": best.get("trade_t_stat"),
            "test_return_pct": round(segment_return, 6),
            "test_round_trips": len(segment_trades),
        })
        step += 1
    n = len(oos_returns)
    mean = sum(oos_returns) / n if n else None
    t_stat = None
    if n > 1:
        std = math.sqrt(sum((r - mean) ** 2 for r in oos_returns) / (n - 1))
        t_stat = round(mean / (std / math.sqrt(n)), 4) if std > 0 else None
    return {
        "strategy_id": options.strategy_id,
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "window_mode": options.window_mode,
        "purge_bars": options.purge_bars,
        "train_bars": options.train_bars,
        "test_bars": options.test_bars,
        "folds": folds,
        "oos_return_pct": round((compounded - 1.0) * 100.0, 6),
        "oos_round_trips": n,
        "oos_avg_trade_net_pct": None if mean is None else round(mean * 100.0, 6),
        "oos_t_stat": t_stat,
        "oos_win_rate": None if not n else round(sum(1 for r in oos_returns if r > 0) / n, 6),
    }


def run_pair_walk_forward(options: PairWalkForwardOptions) -> dict[str, Any]:
    aligned = [normalize_bar(b) for b in align_bars_by_timestamp(options.dominant_bars, options.hedge_bars)]
    min_required = options.train_bars + options.purge_bars + options.test_bars
    if len(aligned) < min_required:
        raise ValueError(f"need at least {min_required} aligned bars, got {len(aligned)}")

    combos = _combos(options.param_grid, options.max_combos)
    folds: list[dict[str, Any]] = []
    compounded = 1.0
    oos_returns: list[float] = []
    step = 0

    while True:
        if options.window_mode == "expanding":
            train_start = 0
            train_end = options.train_bars + step * options.test_bars
        else:
            train_start = step * options.test_bars
            train_end = train_start + options.train_bars

        test_start = train_end + options.purge_bars
        test_end = test_start + options.test_bars
        if test_end > len(aligned):
            break

        train_bars = aligned[train_start:train_end]
        warmup = min(options.warmup_bars, train_end - train_start)
        test_slice = aligned[test_start - warmup : test_end]

        dominant_train = [dict(b) for b in train_bars]
        hedge_train = [{"timestamp": b["timestamp"], "close": b["hedge_close"], "open": b.get("hedge_open", b["hedge_close"])} for b in train_bars]

        dominant_test = [dict(b) for b in test_slice]
        hedge_test = [{"timestamp": b["timestamp"], "close": b["hedge_close"], "open": b.get("hedge_open", b["hedge_close"])} for b in test_slice]

        candidates = []
        for params in combos:
            algo = options.algorithm_factory(**params) if options.algorithm_factory else PairTradingAlgorithm(**params)
            res = run_perp_pair_backtest(
                algo,
                dominant_train,
                hedge_train,
                initial_cash=options.cash,
                fee_rate=options.fee or 0.0,
                slippage_rate=options.slippage or 0.0,
                execution=options.execution,
            )
            candidates.append({"params": params, "return_pct": res.return_pct, "res": res})

        if not candidates:
            raise ValueError("walk-forward: no valid pair parameters")

        candidates.sort(key=lambda c: c["return_pct"], reverse=True)
        best = candidates[0]

        test_algo = options.algorithm_factory(**best["params"]) if options.algorithm_factory else PairTradingAlgorithm(**best["params"])
        test_res = run_perp_pair_backtest(
            test_algo,
            dominant_test,
            hedge_test,
            initial_cash=options.cash,
            fee_rate=options.fee or 0.0,
            slippage_rate=options.slippage or 0.0,
            execution=options.execution,
        )

        segment_return = return_pct_excluding_warmup(test_res.equity_curve, warmup)
        compounded *= 1.0 + segment_return / 100.0
        oos_returns.append(segment_return)

        folds.append({
            "fold_index": step,
            "train_start": int(aligned[train_start]["timestamp"]),
            "train_end": int(aligned[train_end - 1]["timestamp"]),
            "train_bars": train_end - train_start,
            "test_start": int(aligned[test_start]["timestamp"]),
            "test_end": int(aligned[test_end - 1]["timestamp"]),
            "test_bars": options.test_bars,
            "params": best["params"],
            "train_return_pct": round(best["return_pct"], 6),
            "test_return_pct": round(segment_return, 6),
            "trades": len(test_res.trades),
        })
        step += 1

    param_stability: dict[str, Any] = {}
    for p_name in options.param_grid:
        vals = [f["params"].get(p_name) for f in folds if p_name in f["params"]]
        unique_vals = list(set(vals))
        numeric_vals = [float(v) for v in vals if isinstance(v, (int, float))]
        if numeric_vals:
            m = sum(numeric_vals) / len(numeric_vals)
            var = sum((x - m) ** 2 for x in numeric_vals) / len(numeric_vals)
            cv = math.sqrt(var) / m if m != 0 else 0.0
        else:
            m, cv = None, None
        param_stability[p_name] = {
            "values_across_folds": vals,
            "unique_count": len(unique_vals),
            "mean": round(m, 4) if m is not None else None,
            "dispersion_cv": round(cv, 4) if cv is not None else None,
        }

    return {
        "window_mode": options.window_mode,
        "purge_bars": options.purge_bars,
        "execution": options.execution,
        "total_folds": len(folds),
        "folds": folds,
        "oos_return_pct": round((compounded - 1.0) * 100.0, 6),
        "parameter_stability": param_stability,
    }
