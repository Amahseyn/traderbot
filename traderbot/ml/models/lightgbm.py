from __future__ import annotations

from typing import Any

from traderbot.ml.dataset import build_supervised


class LightGBMForecastModel:
    model_id = "lightgbm"

    def __init__(self, **lgbm_params: Any) -> None:
        self._num_boost_round = int(lgbm_params.pop("num_boost_round", lgbm_params.pop("n_estimators", 100)))
        self._params = {
            "objective": "regression",
            "verbosity": -1,
            "num_leaves": 31,
            "learning_rate": 0.05,
            **lgbm_params,
        }
        self._model: Any = None
        self._feature_names: list[str] = []

    def fit(self, xs: list[list[float]], ys: list[float], *, feature_names: list[str]) -> None:
        import lightgbm as lgb
        import numpy as np

        self._feature_names = list(feature_names)
        x_mat = np.asarray(xs, dtype=np.float64)
        y_vec = np.asarray(ys, dtype=np.float64)
        train = lgb.Dataset(x_mat, label=y_vec, feature_name=self._feature_names)
        self._model = lgb.train(self._params, train, num_boost_round=self._num_boost_round)

    def predict(self, xs: list[list[float]]) -> list[float]:
        if self._model is None:
            raise RuntimeError("model not fitted")
        import numpy as np

        x_mat = np.asarray(xs, dtype=np.float64)
        return [float(x) for x in self._model.predict(x_mat)]

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            return {}
        names = self._feature_names or self._model.feature_name()
        values = self._model.feature_importance(importance_type="gain")
        return {str(n): float(v) for n, v in zip(names, values, strict=True)}

    def predict_series(
        self,
        bars: list[dict[str, Any]],
        *,
        horizon_bars: int,
        timestamps: list[int],
    ) -> list[float]:
        xs, _, ts, cols, _ = build_supervised(bars, horizon_bars=horizon_bars)
        idx = {t: i for i, t in enumerate(ts)}
        ordered = [xs[idx[t]] for t in timestamps if t in idx]
        return self.predict(ordered)
