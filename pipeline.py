"""
Merit Order — daily pipeline orchestrator.

Order: ingest (each source isolated) -> upsert store -> derive analytics series ->
render briefing -> build site -> write freshness report. Designed so that ANY source
failing degrades to last-known-good and the site still publishes. Run locally with:

    python pipeline.py            # full run
    python pipeline.py --no-site  # skip the HTML build (data only)
"""
from __future__ import annotations

import json
import math
import sys

import config
from ingest.eia import fetch_eia
from ingest.fred import fetch_fred, fetch_calendar
from ingest.open_meteo import fetch_open_meteo
from ingest.entsoe import fetch_entsoe
from ingest.singapore import fetch_singapore
from analytics import signals
from analytics import macro
from analytics.spreads import generation_cost, fuel_switching_price, clean_spark_spread
from store import load_store, upsert, save_store, history, latest_value
from briefing.render import render_markdown

# Only run the sources that are enabled, so disabled feeds don't clutter the run
# or the freshness report. FRED is the always-on backbone (macro + energy benchmarks).
_REGISTRY = [
    (fetch_fred, True),
    (fetch_eia, config.ENABLE_EIA),
    (fetch_open_meteo, config.ENABLE_OPEN_METEO),
    (fetch_entsoe, config.ENABLE_ENTSOE and bool(config.ENTSOE_TOKEN)),
    (fetch_singapore, config.ENABLE_SINGAPORE),
]
SOURCES = [fn for fn, enabled in _REGISTRY if enabled]


def _latest_date(store, series):
    h = history(store, series)
    return None if h.empty else str(h.iloc[-1]["date"])


def _derive(store):
    """Compute and store derived series so trends accumulate over time.

    Energy and macro derivations are independent: a missing gas feed never blocks
    the macro series, and vice versa. Each derived row is stamped with its own
    source series' latest date.
    """
    import pandas as pd
    derived = []

    def add(series, value, unit, dt):
        if dt is None or value is None or (isinstance(value, float) and math.isnan(value)):
            return
        derived.append({"date": dt, "series": series, "value": float(value),
                        "unit": unit, "source": "derived", "as_of": dt})

    # --- Energy: generation economics keyed off the freshest gas observation ---
    gas = latest_value(store, "gas.henry_hub")
    gas_date = _latest_date(store, "gas.henry_hub")
    if gas is not None:
        add("derived.ccgt_breakeven",
            generation_cost(gas, config.HEAT_RATE_CCGT_US,
                            config.ASSUMED_CARBON_USD_PER_TONNE,
                            config.EF_GAS_TONNE_PER_MWH), "USD/MWh", gas_date)
        add("derived.fuel_switch_carbon",
            fuel_switching_price(gas, config.ASSUMED_COAL_USD_PER_MMBTU,
                                 config.HEAT_RATE_CCGT_US, config.HEAT_RATE_COAL_US,
                                 config.EF_GAS_TONNE_PER_MWH,
                                 config.EF_COAL_TONNE_PER_MWH), "USD/tonne", gas_date)

    # renewable proxies per point (each on its own weather date)
    for p in config.WEATHER_POINTS:
        w = latest_value(store, f"wx.{p}.wind100m")
        s = latest_value(store, f"wx.{p}.shortwave")
        if w is not None:
            add(f"derived.{p}.wind_proxy", signals.wind_power_proxy(w), "frac",
                _latest_date(store, f"wx.{p}.wind100m"))
        if s is not None:
            add(f"derived.{p}.solar_proxy", signals.solar_proxy(s), "frac",
                _latest_date(store, f"wx.{p}.shortwave"))

    # --- Macro: yield-curve slope + the real-yield -> solar-LCOE bridge ---
    y2 = latest_value(store, "rate.ust_2y")
    y10 = latest_value(store, "rate.ust_10y")
    if y2 is not None and y10 is not None:
        add("derived.curve_2s10s", macro.curve_slope_bps(y2, y10), "bps",
            _latest_date(store, "rate.ust_10y"))

    real10 = latest_value(store, "rate.real_10y")
    if real10 is not None:
        add("derived.solar_lcoe",
            macro.lcoe_from_real_yield(real10, config.TRANSITION_WACC_PREMIUM,
                                       config.LCOE_CAPEX_PER_KW, config.LCOE_CAPACITY_FACTOR,
                                       config.LCOE_LIFE_YEARS, config.LCOE_FIXED_OM_PER_KW_YR),
            "USD/MWh", _latest_date(store, "rate.real_10y"))

    # --- Power: live clean spark spreads (power is LIVE; gas/carbon are clearly
    # labelled assumptions — no free daily feed exists for them). Each market is kept
    # in its NATIVE currency so there's no FX noise and nothing is over-claimed. ---
    from analytics.spreads import clean_spark_spread

    # Germany — European convention: gas in EUR/MWh-thermal, heat rate = 1/efficiency.
    de_power = latest_value(store, "power.de_lu")
    if de_power is not None:
        add("derived.de_spark",
            clean_spark_spread(de_power, config.ASSUMED_TTF_EUR_PER_MWH,
                               1.0 / config.SPARK_EFFICIENCY_EU,
                               config.ASSUMED_EUA_EUR_PER_TONNE, config.EF_GAS_TONNE_PER_MWH),
            "EUR/MWh", _latest_date(store, "power.de_lu"))

    # Singapore — native SGD. SG generates from oil-linked LNG, so Henry Hub would
    # badly understate fuel cost; an assumed SG gas price is used, plus the actual
    # Singapore carbon tax. Both clearly flagged as assumptions on the dashboard.
    sg_power = latest_value(store, "power.sg_usep")
    if sg_power is not None:
        add("derived.sg_spark",
            clean_spark_spread(sg_power, config.ASSUMED_SG_GAS_SGD_PER_MMBTU,
                               config.HEAT_RATE_CCGT_SG,
                               config.ASSUMED_SG_CARBON_SGD_PER_TONNE, config.EF_GAS_TONNE_PER_MWH),
            "SGD/MWh", _latest_date(store, "power.sg_usep"))

    if not derived:
        return store
    return upsert(store, pd.DataFrame(derived))


def run(build_site: bool = True) -> None:
    store = load_store()
    report = []

    for src in SOURCES:
        result = src()                      # never raises
        store = upsert(store, result.df)
        report.append(result.summary())
        print(f"[{result.status:>5}] {result.name}: {len(result.df)} rows "
              f"(as_of {result.as_of or '-'}) {result.message}")

    store = _derive(store)
    save_store(store)

    fetch_calendar()   # writes data/_calendar.json (best-effort; [] on failure)

    briefing_md, _ = render_markdown(store)
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    config.BRIEFING_MD.write_text(briefing_md, encoding="utf-8")

    config.FRESHNESS_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if build_site:
        from dashboard.build import build         # imported late so data-only runs are light
        build(store, briefing_md)
        print("site built -> docs/index.html")

    from briefing.email_digest import send_digest   # gated; no-op if email not configured
    print(send_digest(store))

    ok = sum(1 for r in report if r["status"] == "ok")
    print(f"done: {ok}/{len(report)} sources fresh, {len(store)} total rows in store")


if __name__ == "__main__":
    run(build_site="--no-site" not in sys.argv)
