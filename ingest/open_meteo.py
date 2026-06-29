"""
Open-Meteo — free weather, no key required. https://open-meteo.com/

For each sampling point we pull the next ~24h of hourly temperature, 100 m wind
(turbine height) and shortwave radiation, then collapse to one daily row per point:
    wx.<point>.hdd / .cdd / .wind100m / .shortwave
The analytics layer turns these into demand and renewable-output signals.
"""
from __future__ import annotations

import pandas as pd

import config
from ingest.base import http_get_json, safe_source

FORECAST = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,wind_speed_100m,shortwave_radiation"


def _fetch_point(name: str, lat: float, lon: float) -> pd.DataFrame:
    payload = http_get_json(FORECAST, params={
        "latitude": lat, "longitude": lon, "hourly": HOURLY,
        "wind_speed_unit": "ms", "forecast_days": 1, "timezone": "UTC",
    })
    h = payload.get("hourly", {})
    times = h.get("time", [])
    if not times:
        return pd.DataFrame()
    frame = pd.DataFrame({
        "temperature_2m": h.get("temperature_2m", []),
        "wind_speed_100m": h.get("wind_speed_100m", []),
        "shortwave_radiation": h.get("shortwave_radiation", []),
    })
    day = pd.to_datetime(times[0]).strftime("%Y-%m-%d")
    mean_t = frame["temperature_2m"].mean()
    base = config.HDD_CDD_BASE_C
    rows = [
        (f"wx.{name}.hdd", max(0.0, base - mean_t), "degC-day"),
        (f"wx.{name}.cdd", max(0.0, mean_t - base), "degC-day"),
        (f"wx.{name}.wind100m", frame["wind_speed_100m"].mean(), "m/s"),
        (f"wx.{name}.shortwave", frame["shortwave_radiation"].mean(), "W/m2"),
    ]
    return pd.DataFrame(
        [{"date": day, "series": s, "value": float(v), "unit": u, "source": "Open-Meteo"}
         for s, v, u in rows]
    )


@safe_source
def fetch_open_meteo() -> pd.DataFrame:
    if not config.ENABLE_OPEN_METEO:
        return pd.DataFrame()
    frames = []
    for name, p in config.WEATHER_POINTS.items():
        df = _fetch_point(name, p["lat"], p["lon"])
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
