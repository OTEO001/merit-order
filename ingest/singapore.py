"""
Singapore NEMS — the live Uniform Singapore Energy Price (USEP) and system demand.

USEP is the half-hourly wholesale electricity price for Singapore's gas-dominated
grid — directly relevant to a solar/energy desk here. The official EMC API is gated
behind Cloudflare and unusable programmatically, so this reads a community NEMS mirror
that republishes the provisional real-time snapshot as clean JSON. Provisional and
third-party — clearly labelled — and wrapped in @safe_source so any outage degrades
gracefully. Point SG_USEP_URL at another source any time.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config
from ingest.base import http_get_json, safe_source


@safe_source
def fetch_singapore() -> pd.DataFrame:
    if not config.ENABLE_SINGAPORE:
        return pd.DataFrame()

    data = http_get_json(config.SG_USEP_URL)   # {"updated":..,"usep":..,"demand":..,"vcp":..}
    usep = data.get("usep")
    demand = data.get("demand")
    if usep is None:
        return pd.DataFrame()

    # Stamp with the Singapore trading day of the snapshot's update time if present.
    ts = data.get("updated")
    if ts:
        day = datetime.fromtimestamp(int(ts), ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d")
    else:
        day = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d")

    rows = [{"date": day, "series": "power.sg_usep", "value": float(usep),
             "unit": "SGD/MWh", "source": "NEMS"}]
    if demand is not None:
        rows.append({"date": day, "series": "power.sg_demand", "value": float(demand),
                     "unit": "MW", "source": "NEMS"})
    return pd.DataFrame(rows)
