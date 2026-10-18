from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traderbot.backtesting import load_bars_csv
from traderbot.data.intrahour import enrich_bars_for_csv
from traderbot.utils.bars import filter_bars_by_unix_range
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes

MIN_OPTIMIZER_TRAIN_BARS = 40
MIN_COMPARE_EVAL_BARS = 1
DEFAULT_WALK_FORWARD_TRAIN_FRACTION = 0.65


class ResearchWindowError(ValueError):
    """Invalid train/eval split for research optimize + compare."""


def derive_walk_forward_run_start(
    bars: list[dict[str, Any]],
    *,
    train_fraction: float = DEFAULT_WALK_FORWARD_TRAIN_FRACTION,
) -> int | None:
    """Run-start instant that leaves the leading ``train_fraction`` of bars to the optimizer.

    Returns ``None`` when the file is too short to split without starving either side
    (needs at least ``MIN_OPTIMIZER_TRAIN_BARS + MIN_COMPARE_EVAL_BARS`` bars). The
    returned value is a bar open time, so the optimizer trains on bars closing at or
    before it and compare evaluates from it onward — the two windows never overlap.
    """
    count = len(bars)
    if count < MIN_OPTIMIZER_TRAIN_BARS + MIN_COMPARE_EVAL_BARS:
        return None
    split_index = int(count * train_fraction)
    split_index = max(MIN_OPTIMIZER_TRAIN_BARS, split_index)
    split_index = min(split_index, count - MIN_COMPARE_EVAL_BARS)
    return int(bars[split_index]["timestamp"])


@dataclass(frozen=True, slots=True)
class ResearchBarWindows:
    symbol: str | None
    resolution: str | None
    bar_minutes: int
    train_bars: list[dict[str, Any]]
    eval_bars: list[dict[str, Any]]
    run_start_unix_seconds: int | None = None
    auto_split: bool = False


def has_compare_run_window(body: dict[str, Any]) -> bool:
    return body.get("run_start_unix_seconds") is not None or body.get("run_end_unix_seconds") is not None


def validate_research_optimizer_windows(body: dict[str, Any]) -> None:
    """Ensure optimizer data never overlaps the compare run window (walk-forward)."""
    if not body.get("optimize_before_compare"):
        return
    start = body.get("run_start_unix_seconds")
    end = body.get("run_end_unix_seconds")
    # A missing run_start is allowed: each file gets an automatic walk-forward split
    # (see derive_walk_forward_run_start). An explicit start is honored when it leaves
    # enough leading bars, otherwise the split is derived per file too.
    if start is not None and end is not None and start >= end:
        raise ResearchWindowError("run_start_utc must be before run_end_utc")


def preflight_research_csv_paths(
    csv_paths: list[Path],
    body: dict[str, Any],
    strategy_namespace: Any,
    *,
    strategy_ids: list[str],
) -> list[ResearchBarWindows]:
    """Validate every dataset before running optimizers (fail fast, no partial leakage)."""
    if not body.get("optimize_before_compare"):
        return []
    windows_by_csv: list[tuple[Path, ResearchBarWindows]] = []
    for csv_path in csv_paths:
        try:
            windows = load_research_bar_windows(csv_path, body, strategy_namespace)
        except ResearchWindowError as exc:
            raise ResearchWindowError(f"{csv_path.name}: {exc}") from exc
        windows_by_csv.append((csv_path, windows))
    return [item[1] for item in windows_by_csv]


def assert_optimize_sweep_coverage(
    csv_paths: list[Path],
    strategy_ids: list[str],
    sweep_results: list[dict[str, Any]],
) -> None:
    """Every market file and strategy must have a recorded sweep when pre-optimize is enabled."""
    successes = {
        (row.get("csv"), row.get("strategy_id"))
        for row in sweep_results
        if not row.get("skipped") and row.get("best_params")
    }
    missing: list[str] = []
    for csv_path in csv_paths:
        csv_text = str(csv_path)
        for strategy_id in strategy_ids:
            if (csv_text, strategy_id) not in successes:
                missing.append(f"{csv_path.name}:{strategy_id}")
    if missing:
        raise ResearchWindowError(
            "optimizer did not produce params for all market × strategy pairs: "
            + ", ".join(missing)
        )


def validate_terminal_optimizer_no_research_dates(body: dict[str, Any]) -> None:
    """Live/paper terminal tune uses recent exchange candles only — not catalog run windows."""
    if not body.get("optimize_before_run"):
        return
    if bool(body.get("live")):
        raise ResearchWindowError(
            "optimize_before_run is not allowed with live orders; use paper mode or run the "
            "optimizer separately, then enable apply_sweep_winner without optimize_before_run"
        )
    for key in ("run_start_utc", "run_end_utc"):
        if body.get(key) not in (None, ""):
            raise ResearchWindowError(
                f"{key} cannot be combined with optimize_before_run; "
                "live optimizer uses recent closed candles for this market and interval only"
            )
    for key in ("run_start_unix_seconds", "run_end_unix_seconds"):
        if body.get(key) not in (None, ""):
            raise ResearchWindowError(
                "run window bounds cannot be combined with optimize_before_run on terminal jobs"
            )


def _bar_data_unix_bounds(
    raw_bars: list[dict[str, Any]],
    *,
    bar_minutes: int,
) -> tuple[int, int]:
    """First bar open and last bar close (unix seconds)."""
    if not raw_bars:
        return 0, 0
    bar_seconds = bar_minutes * 60
    first_open = int(raw_bars[0]["timestamp"])
    last_close = int(raw_bars[-1]["timestamp"]) + bar_seconds
    return first_open, last_close


def _market_context_from_csv(csv_path: Path) -> tuple[str | None, str | None, int]:
    from traderbot.algorithms.optimized_params import symbol_from_csv_path

    resolution = resolution_from_csv_path(csv_path.name)
    bar_minutes = resolution_minutes(resolution) or 60
    try:
        symbol = symbol_from_csv_path(csv_path)
    except (ValueError, IndexError):
        symbol = None
    return symbol, resolution, bar_minutes


def load_research_bar_windows(
    csv_path: Path,
    body: dict[str, Any],
    strategy_namespace: Any,
) -> ResearchBarWindows:
    """Split OHLC into optimizer train bars (pre-window) and compare eval bars (run window).

    When ``optimize_before_compare`` is set:

    - a usable explicit ``run_start`` (leaving at least ``MIN_OPTIMIZER_TRAIN_BARS``
      leading bars) is honored;
    - otherwise the file gets an automatic walk-forward split
      (:func:`derive_walk_forward_run_start`), so the optimizer never trains on bars
      the compare step will evaluate. The derived instant is returned on the windows
      so the compare step reuses the exact same split.
    """
    raw_bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, strategy_namespace)
    symbol, resolution, bar_minutes = _market_context_from_csv(csv_path)
    run_start = body.get("run_start_unix_seconds")
    run_end = body.get("run_end_unix_seconds")
    optimize_before = bool(body.get("optimize_before_compare"))
    allow_full = bool(body.get("allow_full_history_optimize"))
    auto_split = False

    def _compute_splits(
        *,
        start: int | None,
        end: int | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        eval_slice = filter_bars_by_unix_range(
            raw_bars,
            start_unix_seconds=start,
            end_unix_seconds=end,
            bar_minutes=bar_minutes,
        )
        if start is None and end is None:
            eval_slice = list(raw_bars)
        train_slice: list[dict[str, Any]] = []
        if optimize_before:
            if start is None:
                train_slice = list(raw_bars)
            else:
                train_slice = filter_bars_by_unix_range(
                    raw_bars,
                    start_unix_seconds=None,
                    end_unix_seconds=start,
                    bar_minutes=bar_minutes,
                )
                _assert_no_train_eval_overlap(train_slice, eval_slice, bar_minutes=bar_minutes)
        return train_slice, eval_slice

    if optimize_before and not allow_full:
        train_probe: list[dict[str, Any]] = []
        if run_start is not None:
            train_probe = filter_bars_by_unix_range(
                raw_bars,
                start_unix_seconds=None,
                end_unix_seconds=run_start,
                bar_minutes=bar_minutes,
            )
        if run_start is None or len(train_probe) < MIN_OPTIMIZER_TRAIN_BARS:
            derived = derive_walk_forward_run_start(raw_bars)
            if derived is not None:
                run_start = derived
                auto_split = True

    train_bars, eval_bars = _compute_splits(start=run_start, end=run_end)

    if (
        optimize_before
        and not allow_full
        and len(eval_bars) < MIN_COMPARE_EVAL_BARS
        and len(raw_bars) >= MIN_OPTIMIZER_TRAIN_BARS + MIN_COMPARE_EVAL_BARS
    ):
        if not auto_split:
            derived = derive_walk_forward_run_start(raw_bars)
            if derived is not None:
                run_start = derived
                auto_split = True
                train_bars, eval_bars = _compute_splits(start=run_start, end=run_end)
        if len(eval_bars) < MIN_COMPARE_EVAL_BARS and run_end is not None:
            run_end = None
            train_bars, eval_bars = _compute_splits(start=run_start, end=run_end)

    if optimize_before:
        if len(train_bars) < MIN_OPTIMIZER_TRAIN_BARS:
            label = f"{symbol or csv_path.name}:{resolution or bar_minutes}"
            raise ResearchWindowError(
                f"{label}: need at least {MIN_OPTIMIZER_TRAIN_BARS} bars before run_start for optimizer "
                f"(got {len(train_bars)}); widen history or move run_start later"
            )

    if optimize_before and len(eval_bars) < MIN_COMPARE_EVAL_BARS:
        label = f"{symbol or csv_path.name}:{resolution or bar_minutes}"
        first_open, last_close = _bar_data_unix_bounds(raw_bars, bar_minutes=bar_minutes)
        window_bits: list[str] = []
        if run_start is not None:
            window_bits.append(f"run_start={run_start}")
        if run_end is not None:
            window_bits.append(f"run_end={run_end}")
        window_desc = ", ".join(window_bits) if window_bits else "run window bounds"
        raise ResearchWindowError(
            f"{label}: compare run window has no bars ({window_desc}; "
            f"file spans unix {first_open}–{last_close}, {len(raw_bars)} bars). "
            "Clear the run window on Custom research or align start/end with exported candles."
        )

    return ResearchBarWindows(
        symbol=symbol,
        resolution=resolution,
        bar_minutes=bar_minutes,
        train_bars=train_bars,
        eval_bars=eval_bars,
        run_start_unix_seconds=run_start,
        auto_split=auto_split,
    )


def _assert_no_train_eval_overlap(
    train_bars: list[dict[str, Any]],
    eval_bars: list[dict[str, Any]],
    *,
    bar_minutes: int,
) -> None:
    if not train_bars or not eval_bars:
        return
    bar_seconds = bar_minutes * 60
    last_train_close = int(train_bars[-1]["timestamp"]) + bar_seconds
    first_eval_open = int(eval_bars[0]["timestamp"])
    if last_train_close > first_eval_open:
        raise ResearchWindowError(
            "optimizer train bars overlap the compare window "
            f"(last train close {last_train_close} > first eval open {first_eval_open})"
        )
