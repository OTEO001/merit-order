"""
EIA — the always-free daily backbone: Henry Hub gas spot, WTI and Brent crude.

Uses the EIA v2 "/seriesid/{id}" compatibility route, which returns a legacy series
by its ID with a single key. Get a free instant key at:
    https://www.eia.gov/opendata/register/
Confirm series IDs in the browser: https://www.eia.gov/opendata/browser/
"""
from __future__ import annotations

import pandas as pd

import config
from ingest.base import http_get_json, safe_source

BASE = "https://api.eia.gov/v2/seriesid/{series_id}"


def _fetch_one(series_id: str) -> pd.DataFrame:
    url = BASE.format(series_id=series_id)
    payload = http_get_json(url, params={"api_key": config.EIA_API_KEY})
    rows = payload.get("response", {}).get("data", [])
    out = []
    for r in rows:
        # v2 returns 'period' (date) and 'value'; key names can vary by dataset.
        period = r.get("period")
        value = r.get("value")
        if period is None or value is None:
            continue
        out.append({"period": period, "value": float(value)})
    return pd.DataFrame(out)


@safe_source
def fetch_eia() -> pd.DataFrame:
    if not config.ENABLE_EIA or not config.EIA_API_KEY:
        # No key -> behave like an empty source so safe_source falls back to cache.
        return pd.DataFrame()

    frames = []
    for series, meta in config.EIA_SERIES.items():
        raw = _fetch_one(meta["id"])
        if raw.empty:
            continue
        raw = raw.rename(columns={"period": "date"})
        raw["series"] = series
        raw["unit"] = meta["unit"]
        raw["source"] = "EIA"
        frames.append(raw[["date", "series", "value", "unit", "source"]])

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.sort_values(["series", "date"]).reset_index(drop=True)
