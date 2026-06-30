"""
ENTSO-E Transparency Platform — European day-ahead power prices (genuinely live & free).

Calls the official REST API directly (no heavy client library) and parses the IEC
62325 XML into a single daily-average price for the configured bidding zone. Wrapped
in @safe_source: a missing token or any failure degrades to cache, never raises.

Token (free): register at https://transparency.entsoe.eu/ then request API access
(My Account Settings -> Web API Security Token, or email transparency@entsoe.eu).
Docs: https://documenter.getpostman.com/view/7009892/2s93JtP3F6
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pandas as pd

import config
from ingest.base import http_get_json, safe_source  # http_get_json also returns .text via requests

API = "https://web-api.tp.entsoe.eu/api"


def _parse_prices(xml_text: str) -> list[float]:
    """Pull every <price.amount> out of the A44 publication document."""
    return [float(m) for m in re.findall(r"<price\.amount>([0-9.]+)</price\.amount>", xml_text)]


@safe_source
def fetch_entsoe() -> pd.DataFrame:
    if not config.ENABLE_ENTSOE or not config.ENTSOE_TOKEN:
        return pd.DataFrame()

    import requests
    # Day-ahead prices are published the afternoon before; pull a 48h window around
    # "today" so we always catch the most recent settled day.
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=1)).strftime("%Y%m%d0000")
    end = (now + timedelta(days=1)).strftime("%Y%m%d0000")
    params = {
        "securityToken": config.ENTSOE_TOKEN,
        "documentType": "A44",
        "in_Domain": config.ENTSOE_ZONE,
        "out_Domain": config.ENTSOE_ZONE,
        "periodStart": start,
        "periodEnd": end,
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    prices = _parse_prices(r.text)
    if not prices:
        return pd.DataFrame()

    # Daily average across the returned hourly points (EUR/MWh).
    avg = sum(prices) / len(prices)
    day = now.strftime("%Y-%m-%d")
    return pd.DataFrame([{
        "date": day, "series": "power.de_lu", "value": round(avg, 2),
        "unit": "EUR/MWh", "source": "ENTSO-E",
    }])
