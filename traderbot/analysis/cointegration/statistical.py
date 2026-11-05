from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import scipy.stats as stats

from traderbot.analysis.cointegration.models import RollingHedgeRatioPoint


# -----------------------------------------------------------------------------
# MacKinnon Approximation Surface for ADF & Engle-Granger Cointegration
# -----------------------------------------------------------------------------

def mackinnon_adf_pvalue(stat: float, n_obs: int = 100) -> float:
    """
    Compute finite-sample p-value for the Augmented Dickey-Fuller test
    with constant and no trend (regression='c').
    Uses MacKinnon (1994, 1996) response surface coefficients.
    """
    if not math.isfinite(stat):
        return 1.0

    # Finite sample adjustments for critical values (case 2: constant, no trend)
    # MacKinnon (1996): beta_inf + beta_1 / N + beta_2 / N^2
    crit_01 = -3.4336 - 5.999 / n_obs - 29.25 / (n_obs ** 2)
    crit_05 = -2.8621 - 2.738 / n_obs - 8.36 / (n_obs ** 2)
    crit_10 = -2.5671 - 1.438 / n_obs - 4.48 / (n_obs ** 2)

    if stat <= crit_01:
        # Interpolate below 1%
        # Far left tail: exponential decay
        excess = crit_01 - stat
        p = 0.01 * math.exp(-1.5 * excess)
        return max(1e-6, min(0.01, p))

    if stat <= crit_05:
        # Interpolate between 1% and 5%
        ratio = (stat - crit_01) / (crit_05 - crit_01)
        return 0.01 + 0.04 * ratio

    if stat <= crit_10:
        # Interpolate between 5% and 10%
        ratio = (stat - crit_05) / (crit_10 - crit_05)
        return 0.05 + 0.05 * ratio

    # Above 10% critical value
    # Zero crossing for constant DF distribution is around -0.4 to 0.0
    crit_50 = -0.45 - 0.5 / n_obs
    if stat <= crit_50:
        ratio = (stat - crit_10) / (crit_50 - crit_10)
        return 0.10 + 0.40 * ratio

    # Right tail approaching 1.0
    excess_pos = max(0.0, stat - crit_50)
    p = 0.50 + 0.50 * (1.0 - math.exp(-0.8 * excess_pos))
    return min(1.0, max(0.10, p))


def mackinnon_coint_pvalue(stat: float, n_obs: int = 100) -> float:
    """
    Compute finite-sample p-value for the Engle-Granger cointegration test
    for k=2 variables with constant in the cointegrating equation.
    Uses MacKinnon (1991, 2010) response surface coefficients.
    Crucial: residual-based unit root distribution is shifted significantly left
    compared to raw univariate ADF!
    """
    if not math.isfinite(stat):
        return 1.0

    # MacKinnon (2010) response surface for k=2 with constant:
    # 1%: -3.9001 - 10.534/N - 30.03/N^2
    # 5%: -3.3377 - 5.967/N - 8.98/N^2
    # 10%: -3.0462 - 4.069/N - 5.73/N^2
    crit_01 = -3.9001 - 10.534 / n_obs - 30.03 / (n_obs ** 2)
    crit_05 = -3.3377 - 5.967 / n_obs - 8.98 / (n_obs ** 2)
    crit_10 = -3.0462 - 4.069 / n_obs - 5.73 / (n_obs ** 2)

    if stat <= crit_01:
        excess = crit_01 - stat
        p = 0.01 * math.exp(-1.4 * excess)
        return max(1e-6, min(0.01, p))

    if stat <= crit_05:
        ratio = (stat - crit_01) / (crit_05 - crit_01)
        return 0.01 + 0.04 * ratio

    if stat <= crit_10:
        ratio = (stat - crit_05) / (crit_10 - crit_05)
        return 0.05 + 0.05 * ratio

    # Above 10%
    crit_50 = -1.25 - 1.5 / n_obs
    if stat <= crit_50:
        ratio = (stat - crit_10) / (crit_50 - crit_10)
        return 0.10 + 0.40 * ratio

    excess_pos = max(0.0, stat - crit_50)
    p = 0.50 + 0.50 * (1.0 - math.exp(-0.7 * excess_pos))
    return min(1.0, max(0.10, p))


# -----------------------------------------------------------------------------
# OLS Regression & Hedge Ratio
# -----------------------------------------------------------------------------

def estimate_ols_hedge_ratio(
    y: np.ndarray,
    x: np.ndarray,
) -> tuple[float, float, np.ndarray, float, float]:
    """
    Estimate the cointegrating equation: y = alpha + beta * x + epsilon.
    Returns:
        (alpha, beta, residuals, r_squared, se_beta)
    """
    n = len(y)
    if n < 2 or len(x) != n:
        return 0.0, 0.0, np.zeros_like(y), 0.0, 0.0

    mean_x = float(np.mean(x))
    mean_y = float(np.mean(y))
    dev_x = x - mean_x
    dev_y = y - mean_y

    var_x = float(np.sum(dev_x ** 2))
    var_y = float(np.sum(dev_y ** 2))

    if var_x <= 1e-15:
        # Zero variance in predictor
        return mean_y, 0.0, dev_y, 0.0, 0.0

    cov_xy = float(np.sum(dev_x * dev_y))
    beta = cov_xy / var_x
    alpha = mean_y - beta * mean_x

    residuals = y - (alpha + beta * x)
    rss = float(np.sum(residuals ** 2))

    r_squared = 1.0 - (rss / var_y) if var_y > 1e-15 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))

    df = max(1, n - 2)
    sigma_sq = rss / df
    se_beta = math.sqrt(sigma_sq / var_x) if var_x > 0 else 0.0

    return alpha, beta, residuals, r_squared, se_beta


# -----------------------------------------------------------------------------
# Augmented Dickey-Fuller Test
# -----------------------------------------------------------------------------

def augmented_dickey_fuller_test(
    series: np.ndarray,
    *,
    max_lag: int | None = None,
    include_constant: bool = True,
    autolag: str = "aic",
) -> tuple[float, float, int]:
    """
    Augmented Dickey-Fuller (ADF) test for unit root:
        Delta z_t = [c] + gamma * z_{t-1} + sum_{i=1}^p delta_i * Delta z_{t-i} + e_t
    H0: gamma = 0 (unit root, non-stationary)
    H1: gamma < 0 (stationary)

    Returns:
        (adf_statistic, p_value, selected_lag)
    """
    n = len(series)
    if n < 10:
        return 0.0, 1.0, 0

    diff = np.diff(series)
    n_diff = len(diff)

    default_max = min(12, max(1, int(12.0 * ((n / 100.0) ** 0.25))))
    p_max = default_max if max_lag is None else max(0, min(max_lag, (n_diff - 4) // 2))

    best_stat = 0.0
    best_pvalue = 1.0
    best_lag = 0
    best_ic = float("inf")

    # Evaluate candidate lags
    for p in range(p_max + 1):
        effective_n = n_diff - p
        if effective_n < 5:
            continue

        y_vec = diff[p:]
        z_lag = series[p : p + effective_n]

        cols: list[np.ndarray] = []
        if include_constant:
            cols.append(np.ones(effective_n, dtype=float))
        cols.append(z_lag)

        for lag_idx in range(1, p + 1):
            cols.append(diff[p - lag_idx : p - lag_idx + effective_n])

        X_mat = np.column_stack(cols)
        try:
            # OLS via least squares
            params, residuals_sum, _, _ = np.linalg.lstsq(X_mat, y_vec, rcond=None)
            resids = y_vec - X_mat @ params
            rss = float(np.sum(resids ** 2))
            df = effective_n - X_mat.shape[1]
            if df <= 0 or rss <= 1e-15:
                continue

            sigma_sq = rss / df
            cov_params = np.linalg.inv(X_mat.T @ X_mat) * sigma_sq
            gamma_idx = 1 if include_constant else 0
            se_gamma = math.sqrt(max(1e-15, cov_params[gamma_idx, gamma_idx]))

            gamma = params[gamma_idx]
            adf_stat = float(gamma / se_gamma)

            k_params = X_mat.shape[1]
            if autolag == "bic":
                ic = effective_n * math.log(rss / effective_n) + k_params * math.log(effective_n)
            else:  # aic
                ic = effective_n * math.log(rss / effective_n) + 2.0 * k_params

            if ic < best_ic:
                best_ic = ic
                best_stat = adf_stat
                best_lag = p
                best_pvalue = mackinnon_adf_pvalue(best_stat, n_obs=effective_n)

        except (np.linalg.LinAlgError, ValueError):
            continue

    return best_stat, best_pvalue, best_lag


# -----------------------------------------------------------------------------
# Engle-Granger Two-Step Cointegration Test
# -----------------------------------------------------------------------------

def engle_granger_test(
    log_prices_a: np.ndarray,
    log_prices_b: np.ndarray,
    *,
    max_lag: int | None = None,
) -> tuple[float, float, float, float, np.ndarray, int]:
    """
    Engle-Granger Two-Step Cointegration Procedure:
    Step 1: OLS regression ln(P_A) = alpha + beta * ln(P_B) + epsilon
    Step 2: ADF test on residuals with MacKinnon k=2 cointegration response surface.

    Returns:
        (coint_statistic, coint_pvalue, alpha, beta, spread, selected_lag)
    """
    n = len(log_prices_a)
    if n < 10 or len(log_prices_b) != n:
        return 0.0, 1.0, 0.0, 0.0, np.zeros_like(log_prices_a), 0

    alpha, beta, spread, _, _ = estimate_ols_hedge_ratio(log_prices_a, log_prices_b)

    # In Step 2, run ADF on residuals without constant (residuals have mean 0 by construction)
    adf_stat, _, selected_lag = augmented_dickey_fuller_test(
        spread,
        max_lag=max_lag,
        include_constant=False,
        autolag="aic",
    )

    coint_pvalue = mackinnon_coint_pvalue(adf_stat, n_obs=n)
    return adf_stat, coint_pvalue, alpha, beta, spread, selected_lag


# -----------------------------------------------------------------------------
# Ornstein-Uhlenbeck AR(1) Half-Life Estimation
# -----------------------------------------------------------------------------

def estimate_half_life(spread: np.ndarray) -> tuple[float | None, float, bool]:
    """
    Estimate mean-reversion half-life using Ornstein-Uhlenbeck / AR(1) discretization:
        Delta s_t = s_t - s_{t-1} = c + lambda * s_{t-1} + e_t
    where lambda = -theta * Delta t.
    Continuous half-life: t_{1/2} = -ln(2) / ln(1 + lambda) ~= -ln(2) / lambda.

    Returns:
        (half_life_bars, lambda_param, is_valid)
    """
    n = len(spread)
    if n < 5:
        return None, 0.0, False

    diff = np.diff(spread)
    lag = spread[:-1]

    # OLS regression of Delta s_t on lag s_{t-1} with constant
    mean_lag = float(np.mean(lag))
    mean_diff = float(np.mean(diff))
    dev_lag = lag - mean_lag
    dev_diff = diff - mean_diff

    var_lag = float(np.sum(dev_lag ** 2))
    if var_lag <= 1e-15:
        return None, 0.0, False

    cov_lag_diff = float(np.sum(dev_lag * dev_diff))
    lambda_param = cov_lag_diff / var_lag

    # If lambda >= 0: non-reverting (unit root or explosive)
    if lambda_param >= 0.0:
        return None, float(lambda_param), False

    # If lambda <= -1.0: overshooting oscillation (phi <= 0)
    if lambda_param <= -1.0:
        return None, float(lambda_param), False

    # Mean-reverting Ornstein-Uhlenbeck process
    phi = 1.0 + lambda_param
    half_life = -math.log(2.0) / math.log(phi)

    if not math.isfinite(half_life) or half_life <= 0.0:
        return None, float(lambda_param), False

    return float(half_life), float(lambda_param), True


# -----------------------------------------------------------------------------
# Rolling Hedge Ratio & Stability Analysis
# -----------------------------------------------------------------------------

def compute_rolling_hedge_ratio(
    log_prices_a: np.ndarray,
    log_prices_b: np.ndarray,
    timestamps: list[int],
    *,
    window_bars: int = 60,
    step_bars: int = 5,
) -> tuple[list[RollingHedgeRatioPoint], float]:
    """
    Compute point-in-time rolling OLS hedge ratios and stability metrics.
    Strictly causal: bar t uses only historical observations [t - window_bars + 1, t].

    Returns:
        (rolling_points, stability_score)
    """
    n = len(log_prices_a)
    if n < window_bars or window_bars < 5:
        return [], 0.0

    points: list[RollingHedgeRatioPoint] = []
    betas: list[float] = []

    for end_idx in range(window_bars - 1, n, step_bars):
        start_idx = end_idx - window_bars + 1
        sub_a = log_prices_a[start_idx : end_idx + 1]
        sub_b = log_prices_b[start_idx : end_idx + 1]
        if timestamps:
            if len(timestamps) == n:
                ts = timestamps[end_idx]
            elif end_idx - 1 < len(timestamps) and end_idx >= 1:
                ts = timestamps[end_idx - 1]
            else:
                ts = timestamps[min(end_idx, len(timestamps) - 1)]
        else:
            ts = 0

        alpha, beta, residuals, _, _ = estimate_ols_hedge_ratio(sub_a, sub_b)
        std_spread = float(np.std(residuals))
        adf_stat, _, _ = augmented_dickey_fuller_test(residuals, max_lag=2, include_constant=False)

        points.append(RollingHedgeRatioPoint(
            timestamp=ts,
            hedge_ratio=float(beta),
            intercept=float(alpha),
            spread_std=std_spread,
            adf_statistic=adf_stat,
        ))
        betas.append(beta)

    if len(betas) < 2:
        return points, 1.0

    mean_beta = float(np.mean(betas))
    std_beta = float(np.std(betas))

    # Stability score: penalize coefficient of variation and sign flips
    has_sign_flip = any(b * mean_beta < 0 for b in betas)
    if has_sign_flip:
        stability_score = 0.0
    else:
        cv = std_beta / (abs(mean_beta) + 1e-6)
        stability_score = max(0.0, min(1.0, 1.0 - cv))

    return points, float(stability_score)


# -----------------------------------------------------------------------------
# Structural Break Detection (Chow Test & Mean Divergence)
# -----------------------------------------------------------------------------

def detect_structural_breaks(
    log_prices_a: np.ndarray,
    log_prices_b: np.ndarray,
    spread: np.ndarray,
    *,
    tail_fraction: float = 0.20,
    chow_significance: float = 0.01,
) -> tuple[bool, float, float, list[str]]:
    """
    Detect parameter instability or cointegration breakdown using:
    1. Split-sample Chow F-statistic for structural shift in (alpha, beta).
    2. Spread mean divergence in recent tail window vs historical baseline.

    Returns:
        (has_structural_break, chow_f_stat, chow_pvalue, break_notes)
    """
    n = len(log_prices_a)
    notes: list[str] = []
    if n < 30:
        return False, 0.0, 1.0, ["Insufficient observations for structural break detection"]

    # 1. Chow Test at midpoint
    midpoint = n // 2
    y_full = log_prices_a
    x_full = log_prices_b

    _, _, res_full, _, _ = estimate_ols_hedge_ratio(y_full, x_full)
    _, _, res_1, _, _ = estimate_ols_hedge_ratio(y_full[:midpoint], x_full[:midpoint])
    _, _, res_2, _, _ = estimate_ols_hedge_ratio(y_full[midpoint:], x_full[midpoint:])

    rss_full = float(np.sum(res_full ** 2))
    rss_split = float(np.sum(res_1 ** 2) + np.sum(res_2 ** 2))

    k = 2  # number of parameters (alpha, beta)
    df_num = k
    df_denom = n - 2 * k

    if df_denom <= 0 or rss_split <= 1e-15:
        chow_f = 0.0
        chow_p = 1.0
    else:
        num = max(0.0, (rss_full - rss_split) / df_num)
        denom = rss_split / df_denom
        chow_f = float(num / denom)
        chow_p = float(stats.f.sf(chow_f, df_num, df_denom))

    has_chow_break = bool(chow_p < chow_significance)
    if has_chow_break:
        notes.append(f"Chow structural break detected (F={chow_f:.2f}, p={chow_p:.4e})")

    # 2. Spread Mean & Variance Divergence in recent tail
    tail_len = max(5, int(n * tail_fraction))
    recent_spread = spread[-tail_len:]
    historical_spread = spread[:-tail_len]

    std_hist = float(np.std(historical_spread))
    if std_hist > 1e-15:
        mean_recent = float(np.mean(recent_spread))
        mean_hist = float(np.mean(historical_spread))
        z_divergence = abs(mean_recent - mean_hist) / std_hist
        if z_divergence > 2.5:
            notes.append(f"Spread divergence detected (z={z_divergence:.2f} > 2.5)")
            has_chow_break = True

    return has_chow_break, chow_f, chow_p, notes


# -----------------------------------------------------------------------------
# Benjamini-Hochberg False Discovery Rate Correction
# -----------------------------------------------------------------------------

def benjamini_hochberg_correction(p_values: Sequence[float]) -> list[float]:
    """
    Benjamini-Hochberg procedure to control False Discovery Rate (FDR)
    across multiple candidate cointegration tests:
        q_{(i)} = min_{k >= i} ( min(1.0, (m / k) * p_{(k)}) )
    Returns adjusted p-values in the original input order.
    """
    m = len(p_values)
    if m == 0:
        return []
    if m == 1:
        return [float(p_values[0])]

    # Sort p-values ascending while keeping track of original indices
    sorted_pairs = sorted(enumerate(p_values), key=lambda x: x[1])
    original_indices = [idx for idx, _ in sorted_pairs]
    sorted_p = [p for _, p in sorted_pairs]

    adjusted = [1.0] * m
    cum_min = 1.0

    # Step-down from highest rank m to lowest rank 1
    for rank in range(m, 0, -1):
        idx = rank - 1
        p_val = sorted_p[idx]
        val = (float(m) / float(rank)) * p_val
        cum_min = min(cum_min, val)
        adjusted[idx] = min(1.0, max(0.0, cum_min))

    # Restore original ordering
    result = [0.0] * m
    for sort_idx, orig_idx in enumerate(original_indices):
        result[orig_idx] = adjusted[sort_idx]

    return result
