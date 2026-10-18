"""DRL model selection helpers (no torch / SB3 imports)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def split_validation_for_model_selection(
    validation_df: pd.DataFrame,
    *,
    date_column: str = "date",
    selection_tail_fraction: float = 0.5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if validation_df.empty or date_column not in validation_df.columns:
        return validation_df, validation_df.iloc[0:0]
    dates = sorted(pd.to_datetime(validation_df[date_column].dropna().unique()))
    if len(dates) < 2:
        return validation_df, validation_df.iloc[0:0]
    cut = max(1, int(len(dates) * (1.0 - selection_tail_fraction)))
    holdout_dates = set(dates[:cut])
    selection_dates = set(dates[cut:])
    dt = pd.to_datetime(validation_df[date_column])
    holdout = validation_df.loc[dt.isin(holdout_dates)].copy()
    selection = validation_df.loc[dt.isin(selection_dates)].copy()
    return selection, holdout


def merge_selection_meta(
    scores_selection: dict[str, float],
    scores_holdout: dict[str, float],
    selected: str,
    *,
    selection_tail_fraction: float,
) -> dict[str, Any]:
    return {
        "selection_scores": scores_selection,
        "holdout_scores": scores_holdout,
        "selected": selected,
        "selection_tail_fraction": selection_tail_fraction,
    }
