from __future__ import annotations

from typing import Any, Protocol


class ForecastModel(Protocol):
    model_id: str

    def fit(self, xs: list[list[float]], ys: list[float], *, feature_names: list[str]) -> None: ...

    def predict(self, xs: list[list[float]]) -> list[float]: ...

    def predict_series(
        self,
        bars: list[dict[str, Any]],
        *,
        horizon_bars: int,
        timestamps: list[int],
    ) -> list[float]:
        """Optional path for series models (Chronos). Default: tabular predict on xs."""
        ...
