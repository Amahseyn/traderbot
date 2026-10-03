from __future__ import annotations

from typing import Any

from traderbot.ml.dataset import (
    assert_holdout_is_causal,
    build_supervised,
    train_test_split_holdout_tail_bars,
    train_test_split_temporal,
)
from traderbot.ml.utils import horizon_label, price_series_from_bars
from traderbot.ml.models.base import ForecastModel
from traderbot.ml.models.chronos import ChronosForecastModel
from traderbot.ml.models.lightgbm import LightGBMForecastModel
from traderbot.ml.results import ModelRunResult
from traderbot.ml.simulation_config import SimulationConfig
from traderbot.utils.constants import ONE_MINUTE_BAR_MINUTES


def model_for_id(model_id: str, **kwargs: Any) -> ForecastModel:
    if model_id == "lightgbm":
        return LightGBMForecastModel(**kwargs)
    if model_id == "chronos":
        return ChronosForecastModel(**kwargs)
    raise ValueError(f"unsupported model_id={model_id!r}; implemented: lightgbm, chronos")


def run_forecast_eval(
    bars: list[dict[str, Any]],
    model: ForecastModel,
    *,
    horizon_bars: int,
    bar_minutes = 60,
    train_ratio = 0.8,
    train_supervised_row_count: int | None = None,
    holdout_tail_bars: int | None = None,
    one_minute_bars: list[dict[str, Any]] | None = None,
    one_minute_bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
    simulation_config: SimulationConfig | None = None,
) -> ModelRunResult:
    xs, ys, timestamps, feature_names, label_ends = build_supervised(
        bars,
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        one_minute_bars=one_minute_bars,
        one_minute_bar_minutes=one_minute_bar_minutes,
    )
    if holdout_tail_bars is not None:
        x_train, y_train, ts_train, x_test, y_test, ts_test = train_test_split_holdout_tail_bars(
            xs,
            ys,
            timestamps,
            holdout_tail_bars=holdout_tail_bars,
            bars=bars,
            label_end_timestamps=label_ends,
        )
    else:
        x_train, y_train, ts_train, x_test, y_test, ts_test = train_test_split_temporal(
            xs,
            ys,
            timestamps,
            train_ratio=train_ratio,
            train_supervised_row_count=train_supervised_row_count,
            horizon_bars=horizon_bars,
            label_end_timestamps=label_ends,
        )
    ts_to_label_end = dict(zip(timestamps, label_ends, strict=True))
    train_label_ends = [ts_to_label_end[t] for t in ts_train]
    assert_holdout_is_causal(
        train_timestamps=ts_train,
        test_timestamps=ts_test,
        train_label_end_timestamps=train_label_ends,
    )
    model.fit(x_train, y_train, feature_names=feature_names)

    extra: dict[str, Any] = {
        "supervised_row_count": len(xs),
        "train_supervised_row_count": len(x_train),
        "test_supervised_row_count": len(x_test),
        "train_ratio": train_ratio,
        "train_supervised_row_count_requested": train_supervised_row_count,
        "holdout_tail_bars": holdout_tail_bars,
    }
    if isinstance(model, LightGBMForecastModel):
        extra["feature_importance"] = model.feature_importance()
        y_pred = model.predict(x_test)
    elif isinstance(model, ChronosForecastModel):
        y_pred = model.predict_series(bars, horizon_bars=horizon_bars, timestamps=ts_test)
    else:
        y_pred = model.predict(x_test)

    price_series = price_series_from_bars(bars)

    if simulation_config is None:
        simulation_config = SimulationConfig(horizon_bars=horizon_bars, bar_minutes=bar_minutes)

    return ModelRunResult(
        model_id=model.model_id,
        horizon_label=horizon_label(bar_minutes, horizon_bars),
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        price_series=price_series,
        feature_names=feature_names,
        timestamps=ts_test,
        y_true=y_test,
        y_pred=y_pred,
        extra=extra,
        simulation_config=simulation_config,
    )
