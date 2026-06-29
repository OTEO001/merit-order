"""
seed_demo.py — OPTIONAL local preview helper (not part of the production pipeline).

The live pipeline fills data/series.csv from real APIs. But to preview the
dashboard *before* you have API keys (or offline), this writes ~90 business days
of plausible gas / oil / weather history into the store, so `python pipeline.py`
renders a fully populated site. The values are synthetic and clearly marked with
source="demo" — delete data/series.csv to start clean once your keys are live.

    python seed_demo.py        # then: python pipeline.py
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pandas as pd

import config
from ingest.base import COLUMNS

random.seed(7)   # reproducible preview


def _business_days(n: int):
    days, d = [], date.today()
    while len(days) < n:
        if d.weekday() < 5:        # Mon–Fri only, like spot price series
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def _ar1(n, start, mean, vol, lo, hi):
    """Mean-reverting random walk, clamped — looks like a real commodity series."""
    out, x = [], start
    for _ in range(n):
        x += 0.15 * (mean - x) + random.gauss(0, vol)
        x = max(lo, min(hi, x))
        out.append(round(x, 4))   # keep enough precision for 4-dp FX rates
    return out


def main() -> None:
    days = _business_days(90)
    n = len(days)
    rows = []

    def add(series, values, unit):
        for d, v in zip(days, values):
            rows.append({"date": d.isoformat(), "series": series, "value": float(v),
                         "unit": unit, "source": "demo", "as_of": d.isoformat()})

    # Fuel benchmarks (rough, plausible recent levels).
    gas = _ar1(n, 3.1, 3.2, 0.12, 2.4, 4.6)
    wti = _ar1(n, 73, 74, 1.1, 64, 86)
    brent = [round(w + 3.8 + random.gauss(0, 0.3), 2) for w in wti]   # Brent-WTI quality spread
    add("gas.henry_hub", gas, "USD/MMBtu")
    add("oil.wti", wti, "USD/bbl")
    add("oil.brent", brent, "USD/bbl")

    # Weather per sampling point. Northern-hemisphere points get a mild seasonal
    # temperature; Singapore stays hot. Enough structure for HDD/CDD + renewables.
    seasonal = {"ercot_houston": 24, "ercot_dallas": 21, "de_frankfurt": 12,
                "nl_rotterdam": 11, "sg_singapore": 28}
    for point, base_t in seasonal.items():
        temps = [base_t + 4 * math.sin(i / 14) + random.gauss(0, 1.5) for i in range(n)]
        add(f"wx.{point}.hdd", [max(0.0, config.HDD_CDD_BASE_C - t) for t in temps], "degC-day")
        add(f"wx.{point}.cdd", [max(0.0, t - config.HDD_CDD_BASE_C) for t in temps], "degC-day")
        add(f"wx.{point}.wind100m", _ar1(n, 7, 7, 0.8, 1.5, 16), "m/s")
        sun = [max(0.0, 480 + 180 * math.sin(i / 13) + random.gauss(0, 40)) for i in range(n)]
        add(f"wx.{point}.shortwave", [round(s, 1) for s in sun], "W/m2")

    # --- Macro series (plausible recent levels; synthetic, source="demo") ---
    ust_2y = _ar1(n, 3.90, 3.90, 0.04, 3.3, 4.6)
    ust_10y = _ar1(n, 4.30, 4.30, 0.04, 3.6, 4.9)
    real_10y = _ar1(n, 1.95, 1.95, 0.03, 1.3, 2.5)
    add("rate.ust_3m",  _ar1(n, 4.30, 4.30, 0.03, 3.8, 4.8), "%")
    add("rate.ust_2y",  ust_2y, "%")
    add("rate.ust_5y",  _ar1(n, 4.05, 4.05, 0.04, 3.4, 4.7), "%")
    add("rate.ust_10y", ust_10y, "%")
    add("rate.ust_30y", _ar1(n, 4.55, 4.55, 0.04, 3.9, 5.1), "%")
    add("rate.real_10y", real_10y, "%")
    add("rate.breakeven_10y", _ar1(n, 2.30, 2.30, 0.02, 1.9, 2.7), "%")
    add("rate.fed_funds", _ar1(n, 4.33, 4.33, 0.01, 4.0, 4.6), "%")
    add("rate.sofr",      _ar1(n, 4.31, 4.31, 0.01, 4.0, 4.6), "%")
    add("fx.usd_broad", _ar1(n, 120.0, 120.0, 0.4, 112, 128), "index")
    add("fx.eur_usd",   _ar1(n, 1.08, 1.08, 0.004, 1.02, 1.15), "USD/EUR")
    add("fx.usd_jpy",   _ar1(n, 150.0, 150.0, 0.7, 140, 160), "JPY/USD")
    add("fx.gbp_usd",   _ar1(n, 1.27, 1.27, 0.004, 1.20, 1.34), "USD/GBP")
    add("fx.usd_cny",   _ar1(n, 7.20, 7.20, 0.02, 7.0, 7.4), "CNY/USD")
    add("credit.hy_oas", _ar1(n, 3.20, 3.20, 0.06, 2.6, 5.0), "%")
    add("credit.ig_oas", _ar1(n, 0.90, 0.90, 0.02, 0.7, 1.5), "%")
    add("vol.vix",   _ar1(n, 15.0, 15.0, 0.9, 11, 32), "index")
    add("eq.sp500",  _ar1(n, 5800, 5800, 35, 5200, 6200), "index")
    add("eq.nasdaq", _ar1(n, 18500, 18500, 120, 16500, 20000), "index")

    # --- Derived series, backfilled day-by-day so the preview shows full history.
    # (In production these accumulate one point per run; here we precompute them so
    # sparklines and trends are populated immediately.) ---
    from analytics.spreads import generation_cost, fuel_switching_price
    from analytics import macro
    ccgt = [generation_cost(g, config.HEAT_RATE_CCGT_US,
                            config.ASSUMED_CARBON_USD_PER_TONNE,
                            config.EF_GAS_TONNE_PER_MWH) for g in gas]
    switch = [fuel_switching_price(g, config.ASSUMED_COAL_USD_PER_MMBTU,
                                   config.HEAT_RATE_CCGT_US, config.HEAT_RATE_COAL_US,
                                   config.EF_GAS_TONNE_PER_MWH,
                                   config.EF_COAL_TONNE_PER_MWH) for g in gas]
    slope = [macro.curve_slope_bps(a, b) for a, b in zip(ust_2y, ust_10y)]
    lcoe = [macro.lcoe_from_real_yield(r, config.TRANSITION_WACC_PREMIUM,
                                       config.LCOE_CAPEX_PER_KW, config.LCOE_CAPACITY_FACTOR,
                                       config.LCOE_LIFE_YEARS, config.LCOE_FIXED_OM_PER_KW_YR)
            for r in real_10y]
    add("derived.ccgt_breakeven", [round(v, 2) for v in ccgt], "USD/MWh")
    add("derived.fuel_switch_carbon", [round(v, 2) for v in switch], "USD/tonne")
    add("derived.curve_2s10s", [round(v, 1) for v in slope], "bp")
    add("derived.solar_lcoe", [round(v, 2) for v in lcoe], "USD/MWh")

    df = pd.DataFrame(rows)[COLUMNS]
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.SERIES_CSV, index=False)
    print(f"seeded {len(df)} demo rows across {df['series'].nunique()} series "
          f"-> {config.SERIES_CSV}")


if __name__ == "__main__":
    main()
