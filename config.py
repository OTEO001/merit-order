"""
Central configuration for Merit Order.

Everything tunable lives here so the pipeline modules stay generic. Where a value
is an *assumption* (no free live feed exists for it), it is labelled as such and
surfaced on the dashboard — being explicit about what is measured vs assumed is a
deliberate, desk-grade choice, not a shortcut.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "_cache"
SERIES_CSV = DATA_DIR / "series.csv"          # tidy long store, committed each run
FRESHNESS_JSON = DATA_DIR / "_freshness.json"  # per-source data-quality report
DOCS_DIR = ROOT / "docs"                        # GitHub Pages output
BRIEFING_MD = DOCS_DIR / "briefing.md"
CALENDAR_JSON = DATA_DIR / "_calendar.json"     # upcoming macro data releases

# ---------------------------------------------------------------------------
# Feature toggles  (env-overridable so CI can flip them without code edits)
# ---------------------------------------------------------------------------
def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

ENABLE_EIA = _env_bool("ENABLE_EIA", False)          # optional: EIA-native energy datasets (FRED already covers gas/oil)
ENABLE_FRED = _env_bool("ENABLE_FRED", True)          # PRIMARY backbone: macro + energy benchmarks (needs one key)
ENABLE_OPEN_METEO = _env_bool("ENABLE_OPEN_METEO", True)  # weather (no key)
ENABLE_ENTSOE = _env_bool("ENABLE_ENTSOE", False)    # European power off by default; set ENABLE_ENTSOE=true + ENTSOE_TOKEN to enable
ENABLE_SINGAPORE = _env_bool("ENABLE_SINGAPORE", True)  # Singapore USEP — free community NEMS mirror, no key
ENABLE_LLM_POLISH = _env_bool("ENABLE_LLM_POLISH", False)  # optional briefing rewrite

# ---------------------------------------------------------------------------
# API keys (read from environment / GitHub Actions secrets — NEVER hard-code)
# ---------------------------------------------------------------------------
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
ENTSOE_TOKEN = os.getenv("ENTSOE_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Network behaviour
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = 30          # seconds
HTTP_RETRIES = 3
HTTP_BACKOFF = 2.0         # seconds, multiplied each retry

# ---------------------------------------------------------------------------
# EIA series  (OPTIONAL source — FRED already provides gas/WTI/Brent on one key).
#   The v2 /seriesid/ compatibility route needs the FULL legacy v1 ID, including
#   the dataset prefix and frequency suffix (e.g. NG.RNGWHHD.D), not the bare code.
#   Enable with ENABLE_EIA=true + an EIA key only if you want EIA-native datasets.
#   Free key: https://www.eia.gov/opendata/register/   Browser: https://www.eia.gov/opendata/browser/
# ---------------------------------------------------------------------------
EIA_SERIES = {
    "gas.henry_hub": {"id": "NG.RNGWHHD.D", "unit": "USD/MMBtu"},   # Henry Hub spot, daily
    "oil.wti":       {"id": "PET.RWTC.D",   "unit": "USD/bbl"},      # WTI Cushing spot, daily
    "oil.brent":     {"id": "PET.RBRTE.D",  "unit": "USD/bbl"},      # Brent spot, daily
}

# ---------------------------------------------------------------------------
# Open-Meteo sampling points.
#   Pick a few representative load / wind / solar locations. Defaults below give a
#   Texas (ERCOT) + NW-Europe spread so the weather signal means something on day 1;
#   swap for your target market's population/asset centroids.
# ---------------------------------------------------------------------------
WEATHER_POINTS = {
    "ercot_houston": {"lat": 29.76, "lon": -95.37},
    "ercot_dallas":  {"lat": 32.78, "lon": -96.80},
    "de_frankfurt":  {"lat": 50.11, "lon": 8.68},
    "nl_rotterdam":  {"lat": 51.92, "lon": 4.48},
    "sg_singapore":  {"lat": 1.35,  "lon": 103.82},
}
HDD_CDD_BASE_C = 18.0          # degree-day base temperature (~65F)
WIND_CUT_IN_MS = 3.0
WIND_RATED_MS = 12.0
WIND_CUT_OUT_MS = 25.0
SOLAR_CLEAR_SKY_WM2 = 800.0    # reference irradiance to normalise the solar proxy

# ---------------------------------------------------------------------------
# Plant + emissions parameters.
#   Two heat-rate conventions exist and people mix them up — handle both explicitly:
#     US:     MMBtu of fuel per MWh of electricity  (CCGT ~7.0)
#     Europe: MWh-thermal per MWh-electric = 1/efficiency  (CCGT ~2.0 at 50%)
#   Emissions factors are tonnes CO2 per MWh of *electricity* generated.
# ---------------------------------------------------------------------------
HEAT_RATE_CCGT_US = 7.0        # MMBtu/MWh
HEAT_RATE_OCGT_US = 9.5        # MMBtu/MWh
HEAT_RATE_COAL_US = 9.5        # MMBtu/MWh

EF_GAS_TONNE_PER_MWH = 0.37    # CCGT
EF_COAL_TONNE_PER_MWH = 0.85   # ~2x gas

# ---------------------------------------------------------------------------
# ASSUMPTIONS — no clean free daily feed exists for these. Override via env or a
# manual series when you wire a real source. Clearly flagged on the dashboard.
# ---------------------------------------------------------------------------
ASSUMED_COAL_USD_PER_MMBTU = float(os.getenv("ASSUMED_COAL", "3.0"))
ASSUMED_CARBON_USD_PER_TONNE = float(os.getenv("ASSUMED_CARBON", "0.0"))  # US ~0; EU set ~80

# ---------------------------------------------------------------------------
# Live power markets (the spark spread).
#   Europe: ENTSO-E day-ahead price is genuinely live & free (needs a token).
#     The matching gas (TTF) and carbon (EUA) have no clean free daily feed, so the
#     spark spread uses the LIVE power price against clearly-labelled gas/carbon
#     assumptions — exactly the same honesty pattern as the US CCGT breakeven.
#   Singapore: USEP is the live half-hourly wholesale price via a community NEMS
#     mirror (the official EMC API is Cloudflare-gated). Provisional, clearly noted.
# ---------------------------------------------------------------------------
ENTSOE_ZONE = os.getenv("ENTSOE_ZONE") or "10Y1001A1001A82H"   # DE-LU (Germany), most liquid
ENTSOE_ZONE_NAME = os.getenv("ENTSOE_ZONE_NAME") or "Germany (DE-LU)"
SPARK_EFFICIENCY_EU = 0.50                 # CCGT electrical efficiency -> heat rate 1/eff (MWh_th/MWh_e)
ASSUMED_TTF_EUR_PER_MWH = float(os.getenv("ASSUMED_TTF", "32.0"))   # European gas, EUR/MWh-thermal (assumption)
ASSUMED_EUA_EUR_PER_TONNE = float(os.getenv("ASSUMED_EUA", "70.0"))  # EU carbon, EUR/tonne (assumption)
SG_USEP_URL = os.getenv("SG_USEP_URL", "https://nems.sn.sg/api/status.json")
# Singapore spark-spread inputs — native SGD. SG generates from oil-linked LNG, so an
# assumed local gas price is used (Henry Hub would badly understate it). Carbon is the
# actual Singapore tax: S$45/tCO2e for 2026-2027 (was S$25 in 2024-25). All assumptions.
HEAT_RATE_CCGT_SG = float(os.getenv("HEAT_RATE_CCGT_SG", "7.0"))          # MMBtu/MWh, modern CCGT
ASSUMED_SG_GAS_SGD_PER_MMBTU = float(os.getenv("ASSUMED_SG_GAS", "16.0")) # ~US$12/MMBtu LNG (assumption)
ASSUMED_SG_CARBON_SGD_PER_TONNE = float(os.getenv("ASSUMED_SG_CARBON", "45.0"))  # SG carbon tax, 2026

# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------
ANOMALY_WINDOW = 90            # rolling trading-day window
ANOMALY_Z = 2.0                # |z| above this is flagged "notable"

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------
SITE_TITLE = "Merit Order"
SITE_TAGLINE = "Daily macro & energy-market intelligence — rates, FX, credit, power, gas & oil"
MARKET_TZ = "Asia/Singapore"   # display timezone for the timestamp

# ---------------------------------------------------------------------------
# Daily email digest (optional). Sent via SMTP — works with a Gmail address +
# a 16-character App Password. All driven by env/secrets; if EMAIL_USER and
# EMAIL_PASS are absent the pipeline simply skips sending.
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))     # 465 = SSL
EMAIL_USER = os.getenv("EMAIL_USER", "")           # your Gmail address
EMAIL_PASS = os.getenv("EMAIL_PASS", "")           # Gmail App Password (not your login pw)
EMAIL_TO = os.getenv("EMAIL_TO", "") or EMAIL_USER  # recipient (defaults to yourself)
SITE_URL = os.getenv("SITE_URL", "")               # link back to the live dashboard
ENABLE_EMAIL = bool(EMAIL_USER and EMAIL_PASS)

# ---------------------------------------------------------------------------
# MACRO BACKBONE — FRED (Federal Reserve Bank of St. Louis).
#   FRED is to macro what EIA is to energy: one free, daily, rock-solid feed that
#   covers everything a cross-asset desk watches — the Treasury curve, real yields,
#   inflation breakevens, the dollar and FX majors, IG/HY credit spreads, equity
#   vol, front-end policy rates, and the economic-release calendar.
#   Free instant key:   https://fred.stlouisfed.org/docs/api/api_key.html
#   Verify series IDs:  https://fred.stlouisfed.org/  (search the code, e.g. "DGS10")
#
#   Series IDs are grouped so the analytics and briefing can reason by theme.
# ---------------------------------------------------------------------------
FRED_SERIES = {
    # Treasury curve (constant-maturity yields, %)
    "rate.ust_3m":  {"id": "DGS3MO", "unit": "%",   "group": "rates"},
    "rate.ust_2y":  {"id": "DGS2",   "unit": "%",   "group": "rates"},
    "rate.ust_5y":  {"id": "DGS5",   "unit": "%",   "group": "rates"},
    "rate.ust_10y": {"id": "DGS10",  "unit": "%",   "group": "rates"},
    "rate.ust_30y": {"id": "DGS30",  "unit": "%",   "group": "rates"},
    # Real yields & inflation expectations (the cost-of-capital + breakeven read)
    "rate.real_10y":   {"id": "DFII10", "unit": "%", "group": "rates"},   # 10y TIPS real yield
    "rate.breakeven_10y": {"id": "T10YIE", "unit": "%", "group": "rates"},  # 10y breakeven inflation
    # Policy / money-market front end
    "rate.fed_funds": {"id": "DFF",  "unit": "%", "group": "policy"},      # effective fed funds (daily)
    "rate.sofr":      {"id": "SOFR", "unit": "%", "group": "policy"},
    # The dollar + FX majors  (DTWEXBGS = broad nominal USD index)
    "fx.usd_broad": {"id": "DTWEXBGS", "unit": "index", "group": "fx"},
    "fx.eur_usd":   {"id": "DEXUSEU",  "unit": "USD/EUR", "group": "fx"},  # USD per EUR
    "fx.usd_jpy":   {"id": "DEXJPUS",  "unit": "JPY/USD", "group": "fx"},  # JPY per USD
    "fx.gbp_usd":   {"id": "DEXUSUK",  "unit": "USD/GBP", "group": "fx"},  # USD per GBP
    "fx.usd_cny":   {"id": "DEXCHUS",  "unit": "CNY/USD", "group": "fx"},
    "fx.usd_sgd":   {"id": "DEXSIUS",  "unit": "SGD/USD", "group": "fx"},  # SGD per USD (for SG spark spread)
    # Credit risk (option-adjusted spreads, %)  — the market's risk-appetite gauge
    "credit.hy_oas": {"id": "BAMLH0A0HYM2", "unit": "%", "group": "credit"},  # US high yield
    "credit.ig_oas": {"id": "BAMLC0A0CM",   "unit": "%", "group": "credit"},  # US investment grade
    # Equity vol + index levels  (SP500 carries a licensing lag — labelled, not faked)
    "vol.vix":     {"id": "VIXCLS",    "unit": "index", "group": "equity"},
    "eq.sp500":    {"id": "SP500",     "unit": "index", "group": "equity"},
    "eq.nasdaq":   {"id": "NASDAQCOM", "unit": "index", "group": "equity"},
    # Energy fuel benchmarks — EIA's own daily series, served through FRED so the
    # whole platform runs on a single key. (EIA's native API remains available as an
    # optional source below, for EIA-specific datasets like storage or generation mix.)
    "gas.henry_hub": {"id": "DHHNGSP",      "unit": "USD/MMBtu", "group": "energy"},  # Henry Hub spot, daily
    "oil.wti":       {"id": "DCOILWTICO",   "unit": "USD/bbl",   "group": "energy"},  # WTI Cushing, daily
    "oil.brent":     {"id": "DCOILBRENTEU", "unit": "USD/bbl",   "group": "energy"},  # Brent Europe, daily
}

# Economic-release calendar. FRED's releases/dates endpoint returns upcoming release
# dates with names; we keep the high-impact ones a macro desk actually trades around.
FRED_CALENDAR_KEYWORDS = [
    "Employment Situation",          # non-farm payrolls
    "Consumer Price Index",          # CPI
    "Personal Income and Outlays",   # PCE (the Fed's preferred gauge)
    "Gross Domestic Product",        # GDP
    "FOMC",                          # rate decision / minutes
    "Producer Price Index",          # PPI
    "Retail Sales",
]
CALENDAR_LOOKAHEAD_DAYS = 14
CALENDAR_MAX_EVENTS = 8

# ---------------------------------------------------------------------------
# Cross-asset / risk-regime parameters.
#   The regime score is a transparent, rules-based tally (no black box): each gauge
#   casts a risk-on / risk-off vote and the votes are summed. Thresholds live here.
# ---------------------------------------------------------------------------
VIX_CALM = 15.0          # below -> risk-on vote
VIX_STRESS = 20.0        # above -> risk-off vote
CREDIT_Z_STRESS = 1.0    # HY-spread z-score beyond +/- this casts a vote
REGIME_RISKOFF_AT = 1.5  # summed votes >= this -> "risk-off"
REGIME_RISKON_AT = -1.5  # summed votes <= this -> "risk-on"
CROSS_ASSET_CORR_WINDOW = 30   # rolling window (obs) for USD-vs-commodity correlation

# ---------------------------------------------------------------------------
# Transition-finance bridge (macro -> renewables economics).
#   Real yields set the discount rate for renewable project finance, which flows
#   straight into LCOE via the capital-recovery factor. These stylised parameters
#   let the briefing translate "today's 10y real yield" into "today's solar LCOE",
#   and show the sensitivity to a +100bp move. Clearly labelled stylised inputs.
# ---------------------------------------------------------------------------
LCOE_CAPEX_PER_KW = 1000.0     # stylised utility-scale solar, USD/kW installed
LCOE_CAPACITY_FACTOR = 0.16    # generic tropical/temperate solar capacity factor
LCOE_LIFE_YEARS = 25
LCOE_FIXED_OM_PER_KW_YR = 15.0
TRANSITION_WACC_PREMIUM = 0.045  # spread of project WACC over the 10y real yield
