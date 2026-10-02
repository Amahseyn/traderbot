from __future__ import annotations

from typing import Any

_DEFAULT_MODEL = "amazon/chronos-t5-tiny"


class ChronosForecastModel:
    """
    Amazon Chronos zero-shot forecaster on close prices.

    Requires optional deps: ``pip install -e ".[chronos]"``.
    """

    model_id = "chronos"

    def __init__(self, pretrained: str = _DEFAULT_MODEL, device: str = "cpu") -> None:
        self._pretrained = pretrained
        self._device = device
        self._pipeline: Any = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        from chronos import ChronosPipeline

        self._pipeline = ChronosPipeline.from_pretrained(
            self._pretrained,
            device_map=self._device,
        )

    def fit(self, xs: list[list[float]], ys: list[float], *, feature_names: list[str]) -> None:
        """Pretrained; no fine-tuning in this wrapper."""
        self._load()

    def predict(self, xs: list[list[float]]) -> list[float]:
        raise NotImplementedError("Chronos uses predict_series on OHLCV bars")

    def predict_series(
        self,
        bars: list[dict[str, Any]],
        *,
        horizon_bars: int,
        timestamps: list[int],
    ) -> list[float]:
        import torch

        self._load()
        closes = [float(b["close"]) for b in bars]
        ts_to_idx = {int(b["timestamp"]): i for i, b in enumerate(bars)}
        preds: list[float] = []
        for t in timestamps:
            end = ts_to_idx.get(t)
            if end is None:
                preds.append(0.0)
                continue
            context = torch.tensor(closes[: end + 1], dtype=torch.float32)
            if context.numel() < 2:
                preds.append(0.0)
                continue
            forecast = self._pipeline.predict(context, prediction_length=horizon_bars)
            if hasattr(forecast, "numpy"):
                fc = forecast.numpy()
            else:
                fc = forecast.cpu().numpy()
            # median trajectory, last step vs current close -> log return
            median = fc[0] if fc.ndim > 1 else fc
            if hasattr(median, "__len__"):
                target_price = float(median[-1])
            else:
                target_price = float(median)
            c0 = closes[end]
            if c0 <= 0 or target_price <= 0:
                preds.append(0.0)
            else:
                import math

                preds.append(math.log(target_price / c0))
        return preds
