"""
FRED — the macro backbone: Treasury curve, real yields, breakevens, the dollar &
FX majors, IG/HY credit spreads, equity vol and index levels, policy rates.

Same contract as every other source: returns a tidy DataFrame or, on any failure,
nothing (so @safe_source falls back to last-known-good cache). The economic-release
calendar is fetched separately and written to a small JSON the briefing reads.

Free instant key: https://fred.stlouisfed.org/docs/api/api_key.html
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

import config
from ingest.base import http_get_json, safe_source

OBS = "https://api.stlouisfed.org/fred/series/observations"
RELEASE_DATES = "https://api.stlouisfed.org/fred/releases/dates"


def _fetch_one(series_id: str) -> pd.DataFrame:
    # Pull a trailing slice; FRED returns "." for missing days, which we drop.
    start = (date.today() - timedelta(days=400)).isoformat()
    payload = http_get_json(OBS, params={
        "series_id": series_id, "api_key": config.FRED_API_KEY,
        "file_type": "json", "observation_start": start,
    })
    out = []
    for r in payload.get("observations", []):
        v = r.get("value")
        d = r.get("date")
        if d is None or v in (None, "", "."):
            continue
        try:
            out.append({"date": d, "value": float(v)})
        except ValueError:
            continue
    return pd.DataFrame(out)


@safe_source
def fetch_fred() -> pd.DataFrame:
    if not config.ENABLE_FRED or not config.FRED_API_KEY:
        return pd.DataFrame()      # no key -> empty -> cache fallback

    frames = []
    for series, meta in config.FRED_SERIES.items():
        try:
            raw = _fetch_one(meta["id"])
        except Exception:
            # A single retired/renamed series (FRED returns 400) must never take down
            # the whole feed — skip it and keep every other series flowing.
            continue
        if raw.empty:
            continue
        raw["series"] = series
        raw["unit"] = meta["unit"]
        raw["source"] = "FRED"
        frames.append(raw[["date", "series", "value", "unit", "source"]])

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.sort_values(["series", "date"]).reset_index(drop=True)


def fetch_calendar() -> list[dict]:
    """
    Upcoming high-impact macro releases. Best-effort and self-contained: any failure
    returns [] so the briefing simply omits the calendar rather than breaking.
    Writes config.CALENDAR_JSON as a side effect for the briefing to read.
    """
    events: list[dict] = []
    if not (config.ENABLE_FRED and config.FRED_API_KEY):
        config.CALENDAR_JSON.parent.mkdir(parents=True, exist_ok=True)
        config.CALENDAR_JSON.write_text(json.dumps(events), encoding="utf-8")
        return events

    try:
        today = date.today()
        end = (today + timedelta(days=config.CALENDAR_LOOKAHEAD_DAYS)).isoformat()
        today_s = today.isoformat()
        # include_release_dates_with_no_data=true returns future *scheduled* dates
        # that don't have data yet — exactly the upcoming releases we want.
        payload = http_get_json(RELEASE_DATES, params={
            "api_key": config.FRED_API_KEY, "file_type": "json",
            "include_release_dates_with_no_data": "true",
            "sort_order": "asc", "limit": 1000,
        })
        seen = set()
        for r in payload.get("release_dates", []):
            name = r.get("release_name", "")
            d = r.get("date", "")
            if not name or not d or d < today_s or d > end:
                continue
            if not any(k.lower() in name.lower() for k in config.FRED_CALENDAR_KEYWORDS):
                continue
            key = (name, d)
            if key in seen:
                continue
            seen.add(key)
            events.append({"date": d, "name": name})
        events.sort(key=lambda e: e["date"])
        events = events[: config.CALENDAR_MAX_EVENTS]
    except Exception:
        events = []   # never let the calendar break the run

    config.CALENDAR_JSON.parent.mkdir(parents=True, exist_ok=True)
    config.CALENDAR_JSON.write_text(json.dumps(events), encoding="utf-8")
    return events
