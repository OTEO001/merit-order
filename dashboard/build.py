"""
Build the static dashboard into docs/ for GitHub Pages.

Design: an institutional trading-terminal aesthetic — near-monochrome, dense,
monospaced tabular figures, semantic green/red for moves only, hairline rules. The
signature is the market-data grid: tight grouped tables with inline, server-rendered
SVG sparklines (no per-row JS). Trend panels use thin, muted Plotly lines.

Charts use Plotly.js from CDN so the page stays small; if the CDN is unreachable the
data tables and briefing still render. Everything else is self-contained.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import markdown as md_lib
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from store import history, latest_value
from analytics.spreads import generation_cost, fuel_switching_price
from analytics import macro
from briefing.explain import build_explainers

_env = Environment(
    loader=FileSystemLoader(str(config.ROOT / "dashboard" / "templates")),
    autoescape=select_autoescape(["html"]),
)

# Palette — premium "midnight terminal": semantic green/red, one teal accent.
POS, NEG, MUTED, LINE = "#34D399", "#F87171", "#5C6675", "#1B2230"
ACCENT = "#4FD1C5"


def _fmt(v, nd=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:,.{nd}f}"


def _delta(store, series):
    h = history(store, series)
    if len(h) < 2:
        return None
    return float(h.iloc[-1]["value"]) - float(h.iloc[-2]["value"])


def _spark_svg(vals, direction, w=88, h=22):
    """Tiny inline SVG sparkline of the trailing window. Colour follows direction."""
    vals = [float(v) for v in vals
            if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pad = 2.5
    pts = []
    for i, v in enumerate(vals):
        x = pad + (w - 2 * pad) * i / (n - 1)
        y = pad + (h - 2 * pad) * (1 - (v - lo) / rng)
        pts.append((x, y))
    color = {"pos": POS, "neg": NEG}.get(direction, MUTED)
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.3" '
        f'stroke-linecap="round" stroke-linejoin="round" points="{poly}"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="1.5" fill="{color}"/></svg>'
    )


def _row(store, label, series, unit, nd=2, bp=False, pct=False, win=42):
    """One market-data row: name, last, change (bp or %), sparkline."""
    h = history(store, series)
    last = latest_value(store, series)
    chg = _delta(store, series)

    direction = "flat"
    if chg is not None and not (isinstance(chg, float) and math.isnan(chg)):
        direction = "pos" if chg > 0 else ("neg" if chg < 0 else "flat")

    if chg is None or (isinstance(chg, float) and math.isnan(chg)):
        chg_disp = "—"
    elif bp:
        chg_disp = f"{'+' if chg >= 0 else '-'}{abs(chg) * 100:,.0f} bp"
    elif pct and last is not None and (last - chg) not in (0, None):
        chg_disp = f"{'+' if chg >= 0 else '-'}{abs(chg / (last - chg)) * 100:,.2f}%"
    else:
        chg_disp = f"{'+' if chg >= 0 else '-'}{abs(chg):,.{nd}f}"

    return {
        "label": label, "last": _fmt(last, nd), "unit": unit,
        "chg": chg_disp, "dir": direction,
        "spark": _spark_svg(list(h["value"].tail(win)), direction),
    }


def _hero_stat(store, label, series, unit, nd=2, bp=False, pct=True):
    r = _row(store, label, series, unit, nd, bp=bp, pct=pct)
    raw = latest_value(store, series)
    r["raw"] = "" if raw is None or (isinstance(raw, float) and math.isnan(raw)) else float(raw)
    r["nd"] = nd
    return r


def _chart(store, series, title, unit, color=ACCENT):
    h = history(store, series)
    fig = go.Figure()
    if not h.empty:
        fig.add_trace(go.Scatter(
            x=list(h["date"]), y=[float(v) for v in h["value"]],
            mode="lines", line=dict(color=color, width=1.4),
            hovertemplate="%{y:.2f}<extra></extra>",
        ))
    fig.update_layout(
        margin=dict(l=34, r=8, t=6, b=6), height=140,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False, hovermode="x",
        font=dict(family="IBM Plex Mono, monospace", size=9, color=MUTED),
        xaxis=dict(visible=False),
        yaxis=dict(showgrid=True, gridcolor=LINE, gridwidth=1, nticks=3,
                   tickfont=dict(size=9, color=MUTED), zeroline=False, showline=False),
    )
    return {
        "title": title, "unit": unit,
        "last": _fmt(latest_value(store, series), 2),
        "html": fig.to_html(full_html=False, include_plotlyjs=False,
                            config={"displayModeBar": False, "responsive": True}),
    }


def build(store, briefing_md: str) -> None:
    groups = [
        {"title": "Rates & curve", "rows": [
            _row(store, "2Y", "rate.ust_2y", "%", 2, bp=True),
            _row(store, "10Y", "rate.ust_10y", "%", 2, bp=True),
            _row(store, "30Y", "rate.ust_30y", "%", 2, bp=True),
            _row(store, "10Y real", "rate.real_10y", "%", 2, bp=True),
            _row(store, "2s10s", "derived.curve_2s10s", "bp", 0),
            _row(store, "Breakeven 10Y", "rate.breakeven_10y", "%", 2, bp=True),
        ]},
        {"title": "FX & the dollar", "rows": [
            _row(store, "USD broad", "fx.usd_broad", "idx", 2, pct=True),
            _row(store, "EUR / USD", "fx.eur_usd", "", 4, pct=True),
            _row(store, "USD / JPY", "fx.usd_jpy", "", 2, pct=True),
            _row(store, "GBP / USD", "fx.gbp_usd", "", 4, pct=True),
        ]},
        {"title": "Credit & volatility", "rows": [
            _row(store, "HY OAS", "credit.hy_oas", "%", 2, bp=True),
            _row(store, "IG OAS", "credit.ig_oas", "%", 2, bp=True),
            _row(store, "VIX", "vol.vix", "", 2, pct=True),
            _row(store, "S&P 500", "eq.sp500", "", 0, pct=True),
        ]},
        {"title": "Energy & generation", "rows": [
            _row(store, "Henry Hub", "gas.henry_hub", "$/MMBtu", 2, pct=True),
            _row(store, "WTI", "oil.wti", "$/bbl", 2, pct=True),
            _row(store, "Brent", "oil.brent", "$/bbl", 2, pct=True),
            _row(store, "CCGT b/e", "derived.ccgt_breakeven", "$/MWh", 1),
            _row(store, "Switch carbon", "derived.fuel_switch_carbon", "$/t", 1),
        ]},
    ]

    charts = [
        _chart(store, "rate.ust_10y", "US 10Y yield", "%"),
        _chart(store, "derived.curve_2s10s", "2s10s slope", "bp"),
        _chart(store, "fx.usd_broad", "Broad dollar", "idx"),
        _chart(store, "gas.henry_hub", "Henry Hub gas", "$/MMBtu"),
        _chart(store, "oil.brent", "Brent crude", "$/bbl"),
        _chart(store, "derived.solar_lcoe", "Solar LCOE vs real yields", "$/MWh"),
    ]

    freshness = []
    if config.FRESHNESS_JSON.exists():
        freshness = json.loads(config.FRESHNESS_JSON.read_text())

    data_date = ""
    if not store.empty:
        try:
            data_date = str(sorted(store["date"].astype(str))[-1])
        except Exception:
            data_date = ""

    tz = ZoneInfo(config.MARKET_TZ)
    explainers = build_explainers(store)
    hero_stats = [
        _hero_stat(store, "US 10Y", "rate.ust_10y", "%", 2, bp=True),
        _hero_stat(store, "Broad USD", "fx.usd_broad", "", 2),
        _hero_stat(store, "VIX", "vol.vix", "", 2),
        _hero_stat(store, "Brent", "oil.brent", "$/bbl", 2),
    ]
    html = _env.get_template("index.html.j2").render(
        title=config.SITE_TITLE, tagline=config.SITE_TAGLINE,
        generated_at=datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z"),
        data_date=data_date, groups=groups, charts=charts, freshness=freshness,
        headline=explainers["headline"], sections=explainers["sections"],
        glossary=explainers["glossary"], hero_stats=hero_stats,
        briefing_html=md_lib.markdown(briefing_md, extensions=["tables"]),
    )
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (config.DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
