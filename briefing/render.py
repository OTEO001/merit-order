"""
Daily briefing generator.

Two layers, deliberately decoupled for reliability:
  1. A deterministic Jinja note built entirely from computed numbers + rule-based
     commentary. This always ships.
  2. An OPTIONAL LLM polish pass (Anthropic) that rewrites the deterministic note into
     fluent desk prose. If the key is absent or the call fails, layer 1 ships unchanged.

The model never invents numbers — it only restyles facts the pipeline already computed.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from analytics import signals
from analytics import macro
from analytics.spreads import generation_cost, fuel_switching_price
from store import history, latest_value

_env = Environment(
    loader=FileSystemLoader(str(config.ROOT / "briefing" / "templates")),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True, lstrip_blocks=True,
)


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:,.{nd}f}"


def _delta(store, series):
    h = history(store, series)
    if len(h) < 2:
        return None
    return float(h.iloc[-1]["value"]) - float(h.iloc[-2]["value"])


def _aligned(store, a, b):
    """Return two date-aligned value series for an honest cross-asset correlation."""
    ha = history(store, a)[["date", "value"]].rename(columns={"value": "a"})
    hb = history(store, b)[["date", "value"]].rename(columns={"value": "b"})
    if ha.empty or hb.empty:
        return None, None
    m = ha.merge(hb, on="date", how="inner").sort_values("date")
    return m["a"], m["b"]


def _calendar_facts() -> list[dict]:
    """Read the upcoming-releases JSON the pipeline wrote; annotate days-until."""
    try:
        events = json.loads(config.CALENDAR_JSON.read_text())
    except Exception:
        return []
    today = date.today()
    out = []
    for e in events:
        try:
            d = date.fromisoformat(e["date"])
        except Exception:
            continue
        days = (d - today).days
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days}d")
        out.append({"date": e["date"], "name": e["name"], "when": when})
    return out


def _macro_facts(store) -> dict:
    y2 = latest_value(store, "rate.ust_2y")
    y10 = latest_value(store, "rate.ust_10y")
    real10 = latest_value(store, "rate.real_10y")
    be10 = latest_value(store, "rate.breakeven_10y")
    usd = latest_value(store, "fx.usd_broad")
    hy = latest_value(store, "credit.hy_oas")
    ig = latest_value(store, "credit.ig_oas")
    vix = latest_value(store, "vol.vix")

    slope = macro.curve_slope_bps(y2, y10) if (y2 is not None and y10 is not None) else math.nan
    inverted = macro.is_inverted(slope)

    # Risk regime: transparent rules-based tally over vol, credit, dollar, curve.
    hy_z = signals.rolling_zscore(history(store, "credit.hy_oas")["value"])
    dxy_chg = _delta(store, "fx.usd_broad")
    d2 = _delta(store, "rate.ust_2y")
    d10 = _delta(store, "rate.ust_10y")
    curve_chg = ((d10 - d2) * 100.0) if (d2 is not None and d10 is not None) else math.nan
    regime, regime_score = macro.risk_regime(
        vix if vix is not None else math.nan,
        hy_z, dxy_chg if dxy_chg is not None else math.nan, curve_chg)

    # Real-yield -> solar-LCOE bridge, plus the +100bp sensitivity.
    lcoe_now = macro.lcoe_from_real_yield(
        real10, config.TRANSITION_WACC_PREMIUM, config.LCOE_CAPEX_PER_KW,
        config.LCOE_CAPACITY_FACTOR, config.LCOE_LIFE_YEARS,
        config.LCOE_FIXED_OM_PER_KW_YR) if real10 is not None else math.nan
    lcoe_up = macro.lcoe_from_real_yield(
        real10 + 1.0, config.TRANSITION_WACC_PREMIUM, config.LCOE_CAPEX_PER_KW,
        config.LCOE_CAPACITY_FACTOR, config.LCOE_LIFE_YEARS,
        config.LCOE_FIXED_OM_PER_KW_YR) if real10 is not None else math.nan
    lcoe_delta = (lcoe_up - lcoe_now) if not (math.isnan(lcoe_now) or math.isnan(lcoe_up)) else math.nan

    # Classic cross-asset link: broad dollar vs Brent, correlation of daily changes.
    aa, bb = _aligned(store, "fx.usd_broad", "oil.brent")
    usd_brent_corr = (signals.rolling_corr(aa, bb, config.CROSS_ASSET_CORR_WINDOW)
                      if aa is not None else math.nan)

    return {
        "ust_2y": _fmt(y2), "ust_10y": _fmt(y10),
        "ust_10y_delta": _fmt((d10 * 100) if d10 is not None else None, 0),  # in bps
        "real_10y": _fmt(real10), "breakeven_10y": _fmt(be10),
        "curve_2s10s": _fmt(slope, 0), "inverted": inverted,
        "usd_broad": _fmt(usd), "usd_broad_delta": _fmt(dxy_chg),
        "eur_usd": _fmt(latest_value(store, "fx.eur_usd"), 4),
        "usd_jpy": _fmt(latest_value(store, "fx.usd_jpy"), 2),
        "hy_oas": _fmt(hy), "ig_oas": _fmt(ig),
        "vix": _fmt(vix), "vix_delta": _fmt(_delta(store, "vol.vix")),
        "sp500": _fmt(latest_value(store, "eq.sp500"), 0),
        "regime": regime, "regime_score": _fmt(regime_score, 1),
        "lcoe_now": _fmt(lcoe_now, 1), "lcoe_up": _fmt(lcoe_up, 1),
        "lcoe_delta": _fmt(lcoe_delta, 1),
        "real_for_lcoe": _fmt(real10, 2),
        "usd_brent_corr": _fmt(usd_brent_corr, 2),
        "has_macro": any(v is not None for v in [y10, usd, hy, vix]),
    }


def build_facts(store) -> dict:
    gas = latest_value(store, "gas.henry_hub")
    brent = latest_value(store, "oil.brent")
    wti = latest_value(store, "oil.wti")

    ccgt_cost = generation_cost(
        gas, config.HEAT_RATE_CCGT_US,
        config.ASSUMED_CARBON_USD_PER_TONNE, config.EF_GAS_TONNE_PER_MWH
    ) if gas is not None else math.nan

    switch = fuel_switching_price(
        gas, config.ASSUMED_COAL_USD_PER_MMBTU,
        config.HEAT_RATE_CCGT_US, config.HEAT_RATE_COAL_US,
        config.EF_GAS_TONNE_PER_MWH, config.EF_COAL_TONNE_PER_MWH,
    ) if gas is not None else math.nan

    # Weather signal: aggregate cooling/heating pressure + a renewables read.
    cdd_total = sum(
        (latest_value(store, f"wx.{p}.cdd") or 0.0) for p in config.WEATHER_POINTS
    )
    hdd_total = sum(
        (latest_value(store, f"wx.{p}.hdd") or 0.0) for p in config.WEATHER_POINTS
    )
    wind_vals = [latest_value(store, f"wx.{p}.wind100m") for p in config.WEATHER_POINTS]
    wind_vals = [v for v in wind_vals if v is not None]
    wind_proxy = (
        sum(signals.wind_power_proxy(v) for v in wind_vals) / len(wind_vals)
        if wind_vals else math.nan
    )

    # Anomaly scan across the headline series.
    flags = []
    for s in ["gas.henry_hub", "oil.brent", "oil.wti"]:
        z = signals.rolling_zscore(history(store, s)["value"])
        if signals.is_anomaly(z):
            flags.append({"series": s, "z": round(z, 2)})

    tz = ZoneInfo(config.MARKET_TZ)
    facts = {
        "as_of": datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z"),
        "gas": _fmt(gas), "gas_delta": _fmt(_delta(store, "gas.henry_hub")),
        "brent": _fmt(brent), "brent_delta": _fmt(_delta(store, "oil.brent")),
        "wti": _fmt(wti), "wti_delta": _fmt(_delta(store, "oil.wti")),
        "ccgt_cost": _fmt(ccgt_cost), "switch": _fmt(switch, 1),
        "carbon_now": _fmt(config.ASSUMED_CARBON_USD_PER_TONNE, 1),
        "cdd": _fmt(cdd_total, 1), "hdd": _fmt(hdd_total, 1),
        "wind_proxy_pct": _fmt((wind_proxy * 100) if not math.isnan(wind_proxy) else math.nan, 0),
        "flags": flags,
        "title": config.SITE_TITLE,
    }
    facts.update(_macro_facts(store))
    facts["calendar"] = _calendar_facts()
    return facts


def render_markdown(store) -> tuple[str, dict]:
    facts = build_facts(store)
    md = _env.get_template("briefing.md.j2").render(**facts)
    md = _maybe_polish(md, facts)
    return md, facts


def _maybe_polish(md: str, facts: dict) -> str:
    if not (config.ENABLE_LLM_POLISH and config.ANTHROPIC_API_KEY):
        return md
    try:
        import anthropic  # optional dependency; absence simply disables polish
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        prompt = (
            "Rewrite the following energy-markets morning note in the crisp, neutral "
            "voice of a trading-desk analyst. Keep every number exactly as given, keep "
            "the section structure, do not add facts or speculation.\n\n" + md
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",   # cheap; bump to sonnet for richer prose
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text.strip() or md
    except Exception:
        return md   # any failure -> deterministic note ships untouched
