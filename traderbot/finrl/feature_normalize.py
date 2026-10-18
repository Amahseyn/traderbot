"""Point-in-time feature normalization (no strategy imports)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def zscore_normalize_indicators(
    df: pd.DataFrame,
    indicators: list[str],
    *,
    fit_end_date: pd.Timestamp | None = None,
    date_column: str = "date",
) -> pd.DataFrame:
    df = df.copy()
    fit_mask = pd.Series(True, index=df.index)
    if fit_end_date is not None and date_column in df.columns:
        fit_mask = pd.to_datetime(df[date_column]) <= pd.to_datetime(fit_end_date)
    for col in indicators:
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        fit_vals = vals.loc[fit_mask]
        mu = fit_vals.mean(skipna=True)
        sigma = fit_vals.std(skipna=True)
        if sigma and sigma > 0:
            df[col] = (vals - mu) / sigma
        else:
            df[col] = 0.0
    return df
