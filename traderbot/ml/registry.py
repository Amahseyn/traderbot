from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    """Reference model for crypto OHLCV forecasting (training wiring varies by family)."""

    id: str
    name: str
    rating: int
    summary: str
    pros: tuple[str, ...]
    implemented: bool = False


MODEL_CATALOG: tuple[ModelCatalogEntry, ...] = (
    ModelCatalogEntry(
        id="xgboost",
        name="XGBoost",
        rating=5,
        summary="Strong tabular baseline on OHLCV + technicals; predicts forward returns (e.g. 4h / 24h).",
        pros=("Fast", "Stable", "Explainable", "Works with smaller datasets"),
    ),
    ModelCatalogEntry(
        id="lightgbm",
        name="LightGBM",
        rating=5,
        summary="Often beats XGBoost on tabular crypto features; lower memory and faster training.",
        pros=("Faster training", "Lower memory", "Excellent on tabular features"),
        implemented=True,
    ),
    ModelCatalogEntry(
        id="tft",
        name="Temporal Fusion Transformer",
        rating=5,
        summary="Multi-horizon deep model for price, volume, funding, and exogenous series.",
        pros=("Multi-horizon", "Attention", "Interpretable attention weights"),
    ),
    ModelCatalogEntry(
        id="patchtst",
        name="PatchTST",
        rating=5,
        summary="Patch-based transformer; strong pure time-series benchmarks vs LSTM/GRU.",
        pros=("Transformer-based", "Efficient", "Strong on long horizons"),
    ),
    ModelCatalogEntry(
        id="timesfm",
        name="TimesFM",
        rating=4,
        summary="Google foundation model; zero-shot and few-shot when proprietary data is limited.",
        pros=("Zero-shot", "Few-shot", "No huge dataset required"),
    ),
    ModelCatalogEntry(
        id="chronos",
        name="Chronos (Amazon)",
        rating=4,
        summary="Pretrained foundation forecaster on univariate close; good for quick experiments.",
        pros=("Pretrained", "Small-data friendly", "Easy to try"),
        implemented=True,
    ),
)


def list_models(*, implemented_only: bool = False) -> list[ModelCatalogEntry]:
    if implemented_only:
        return [m for m in MODEL_CATALOG if m.implemented]
    return list(MODEL_CATALOG)
