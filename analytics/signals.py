"""
Fundamentals signals and anomaly detection — pure, NaN-safe functions.

Weather drives both sides of the balance, so cheap proxies go a long way:
  - HDD/CDD       -> heating / cooling demand pressure
  - wind proxy    -> turbine output (power scales with the cube of wind speed)
  - solar proxy   -> PV output (tracks irradiance)
Anomaly flags use a rolling z-score so "notable move" means notable *for this series*.
"""
from __future__ import annotations

import math

import pandas as pd

import config


def hdd(mean_temp: float, base: float = config.HDD_CDD_BASE_C) -> float:
    return max(0.0, base - mean_temp)


def cdd(mean_temp: float, base: float = config.HDD_CDD_BASE_C) -> float:
    return max(0.0, mean_temp - base)


def wind_power_proxy(wind_ms: float) -> float:
    """
    Normalised 0..1 turbine output. Cubic ramp between cut-in and rated, flat at rated
    until cut-out, zero outside the operating band — the brutal non-linearity that makes
    wind forecasting so consequential for price.
    """
    if wind_ms is None or (isinstance(wind_ms, float) and math.isnan(wind_ms)):
        return math.nan
    ci, rated, co = config.WIND_CUT_IN_MS, config.WIND_RATED_MS, config.WIND_CUT_OUT_MS
    if wind_ms < ci or wind_ms >= co:
        return 0.0
    if wind_ms >= rated:
        return 1.0
    return (wind_ms ** 3 - ci ** 3) / (rated ** 3 - ci ** 3)


def solar_proxy(shortwave_wm2: float) -> float:
    """Normalised 0..1 PV output, irradiance clamped to a clear-sky reference."""
    if shortwave_wm2 is None or (isinstance(shortwave_wm2, float) and math.isnan(shortwave_wm2)):
        return math.nan
    return min(1.0, max(0.0, shortwave_wm2 / config.SOLAR_CLEAR_SKY_WM2))


def rolling_zscore(values: pd.Series, window: int = config.ANOMALY_WINDOW) -> float:
    """z-score of the latest observation vs the trailing window. NaN if too short."""
    s = pd.to_numeric(values, errors="coerce").dropna()
    if len(s) < max(10, window // 3):
        return math.nan
    tail = s.tail(window)
    mu, sd = tail.mean(), tail.std(ddof=0)
    if sd == 0 or math.isnan(sd):
        return math.nan
    return float((s.iloc[-1] - mu) / sd)


def percentile_rank(values: pd.Series, window: int = config.ANOMALY_WINDOW) -> float:
    """Percentile (0-100) of the latest value within the trailing window."""
    s = pd.to_numeric(values, errors="coerce").dropna()
    if len(s) < 5:
        return math.nan
    tail = s.tail(window)
    return float((tail <= s.iloc[-1]).mean() * 100.0)


def is_anomaly(z: float, threshold: float = config.ANOMALY_Z) -> bool:
    return (z is not None) and (not math.isnan(z)) and (abs(z) >= threshold)


def rolling_corr(a: pd.Series, b: pd.Series, window: int) -> float:
    """
    Correlation of day/day changes in two aligned series over the trailing window.
    Used for cross-asset reads (e.g. the broad dollar vs Brent). NaN if too short.
    """
    da = pd.to_numeric(a, errors="coerce").reset_index(drop=True).diff()
    db = pd.to_numeric(b, errors="coerce").reset_index(drop=True).diff()
    n = min(len(da), len(db))
    if n < max(8, window // 3):
        return math.nan
    da, db = da.tail(window), db.tail(window)
    pair = pd.concat([da.reset_index(drop=True), db.reset_index(drop=True)], axis=1).dropna()
    if len(pair) < 8 or pair.iloc[:, 0].std() == 0 or pair.iloc[:, 1].std() == 0:
        return math.nan
    return float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
