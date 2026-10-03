from __future__ import annotations

from typing import Any

from traderbot.data.intrahour import intrahour_features_for_coarse_bars
from traderbot.ml.features import INTRAHOUR_BAR_KEYS, build_feature_rows, forward_log_return
from traderbot.ml.utils import horizon_label
from traderbot.utils.constants import ONE_MINUTE_BAR_MINUTES

FEATURE_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "return_1",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "atr_14",
)

OPTIONAL_FEATURE_COLUMNS = (
    "funding_rate",
    "open_interest",
    "volume_delta",
    "market_breadth",
)


def build_supervised(
    bars: list[dict[str, Any]],
    *,
    horizon_bars: int,
    bar_minutes = 60,
    min_rsi_index = 30,
    one_minute_bars: list[dict[str, Any]] | None = None,
    one_minute_bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
) -> tuple[list[list[float]], list[float], list[int], list[str], list[int]]:
    """
    Tabular (X, y) for forward log-return prediction.

    Rows with missing indicators or targets are dropped. Feature order is stable
    (base columns, then any optional columns present in the data).

    ``label_end_timestamps[i]`` is the bar time when ``ys[i]`` is fully known
    (close at ``t + horizon``). Use with :func:`train_test_split_temporal` to
    purge training rows whose labels overlap the holdout period.
    """
    feature_rows = build_feature_rows(
        bars,
        intrahour_features=(
            intrahour_features_for_coarse_bars(
                bars,
                one_minute_bars,
                coarse_minutes=bar_minutes,
                one_minute_bar_minutes=one_minute_bar_minutes,
            )
            if one_minute_bars
            else None
        ),
    )
    closes = [float(b["close"]) for b in bars]
    targets = forward_log_return(closes, horizon_bars)
    optional = [c for c in OPTIONAL_FEATURE_COLUMNS if any(c in r for r in feature_rows)]
    intrahour = [c for c in INTRAHOUR_BAR_KEYS if any(c in r and r.get(c) is not None for r in feature_rows)]
    columns = list(FEATURE_COLUMNS) + intrahour + optional

    xs: list[list[float]] = []
    ys: list[float] = []
    timestamps: list[int] = []
    label_end_timestamps: list[int] = []
    for i, row in enumerate(feature_rows):
        if i < min_rsi_index:
            continue
        y = targets[i]
        if y is None:
            continue
        vals: list[float] = []
        skip = False
        for c in columns:
            v = row.get(c)
            if v is None:
                skip = True
                break
            vals.append(float(v))
        if skip:
            continue
        xs.append(vals)
        ys.append(y)
        timestamps.append(int(row["timestamp"]))
        label_end_timestamps.append(int(bars[i + horizon_bars]["timestamp"]))
    return xs, ys, timestamps, columns, label_end_timestamps


def train_test_split_temporal(
    xs: list[list[float]],
    ys: list[float],
    timestamps: list[int],
    *,
    train_ratio = 0.8,
    horizon_bars = 0,
    label_end_timestamps: list[int] | None = None,
) -> tuple[list[list[float]], list[float], list[int], list[list[float]], list[float], list[int]]:
    """
    Time-ordered train / holdout split.

    With ``horizon_bars > 0``, training only uses rows whose forward-return
    label is fully realized before the first holdout row (index embargo).
    Holdout rows are never included in training.
    """
    if not (0.0 < train_ratio < 1.0):
        raise ValueError("train_ratio must be in (0, 1)")
    n = len(xs)
    if n != len(ys) or n != len(timestamps):
        raise ValueError("xs, ys, and timestamps length mismatch")
    if label_end_timestamps is not None and len(label_end_timestamps) != n:
        raise ValueError("label_end_timestamps length mismatch")
    if horizon_bars < 0:
        raise ValueError("horizon_bars must be >= 0")

    split = max(1, int(n * train_ratio))
    if split >= n:
        split = n - 1

    if horizon_bars <= 0 and label_end_timestamps is None:
        return (
            xs[:split],
            ys[:split],
            timestamps[:split],
            xs[split:],
            ys[split:],
            timestamps[split:],
        )

    def partition(split_at: int) -> tuple[list[int], list[int]]:
        if horizon_bars > 0:
            train_idx = [i for i in range(n) if i + horizon_bars < split_at]
        else:
            test_start_ts = timestamps[split_at]
            train_idx = [
                i for i in range(n) if timestamps[i] < test_start_ts and label_end_timestamps[i] < test_start_ts
            ]
        test_idx = [i for i in range(n) if i >= split_at]
        return train_idx, test_idx

    train_idx, test_idx = partition(split)
    while (not train_idx or not test_idx) and split < n - 1:
        split += 1
        train_idx, test_idx = partition(split)
    if not train_idx or not test_idx:
        raise ValueError("purge left empty train or test set; need more bars or lower train_ratio")

    def take(idxs: list[int]) -> tuple[list[list[float]], list[float], list[int]]:
        return (
            [xs[i] for i in idxs],
            [ys[i] for i in idxs],
            [timestamps[i] for i in idxs],
        )

    x_tr, y_tr, ts_tr = take(train_idx)
    x_te, y_te, ts_te = take(test_idx)
    return x_tr, y_tr, ts_tr, x_te, y_te, ts_te


def assert_holdout_is_causal(
    *,
    train_timestamps: list[int],
    test_timestamps: list[int],
    train_label_end_timestamps: list[int],
) -> None:
    """Raise ``AssertionError`` if holdout design leaks future labels into training."""
    if not test_timestamps:
        raise AssertionError("holdout set is empty")
    test_start = min(test_timestamps)
    if train_timestamps and max(train_timestamps) >= test_start:
        raise AssertionError("training features must be strictly before holdout start")
    for end_ts in train_label_end_timestamps:
        if end_ts >= test_start:
            raise AssertionError("training label realized during holdout (horizon leakage)")
