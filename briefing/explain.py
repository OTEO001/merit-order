"""
Explanation engine — turns the day's numbers into plain-English teaching.

Everything here is rules-based (no LLM): it reads the latest values, classifies the
state of each gauge against simple thresholds, and selects clear, accurate prose that
explains *what* each thing is, *what it's doing today*, and *why it matters* — with a
deliberate through-line to energy and the transition. The same output feeds the
dashboard's explainer panels and the morning email, so the reader learns the markets
a little more each day.
"""
from __future__ import annotations

import hashlib
import math

import config
from analytics import macro, signals
from store import history, latest_value


def _day_seed(store, salt: str = "") -> int:
    """Deterministic per-day int so copy varies day-to-day but is stable within a
    day (no flicker on rebuild) and reproducible in tests."""
    h = history(store, "rate.ust_10y")
    key = (str(h.iloc[-1]["date"]) if not h.empty else "seed") + salt
    return int(hashlib.md5(key.encode()).hexdigest(), 16)


def _pick(pool: list[str], seed: int) -> str:
    return pool[seed % len(pool)] if pool else ""


def _v(store, s):
    return latest_value(store, s)


def _delta(store, s):
    h = history(store, s)
    if len(h) < 2:
        return None
    return float(h.iloc[-1]["value"]) - float(h.iloc[-2]["value"])


def _word(chg, up="rose", down="fell", flat="was little changed", eps=1e-9):
    if chg is None or abs(chg) <= eps:
        return flat
    return up if chg > 0 else down


def _num(v, nd=2, dash="—"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return dash
    return f"{v:,.{nd}f}"


def _mood(regime: str, score: float) -> dict:
    """Trading-desk-flavored framing of the risk regime — same underlying rules-based
    score, sharper language. tag is the short badge; sub is the one-line why."""
    if regime == "risk-off":
        tag = "Risk-Off" if score < 2.5 else "Risk-Off, Loudly"
        sub = "credit's leaking, vol's bid, the dollar's catching a haven flow."
        icon = "down"
    elif regime == "risk-on":
        tag = "Risk-On" if score > -2.5 else "Risk-On, No Brakes"
        sub = "spreads are tight, vol's cheap, nobody's paying for protection."
        icon = "up"
    elif regime == "unknown":
        tag, sub, icon = "No Read", "not enough live data to call it today.", "flat"
    else:
        tag = "Chop"
        sub = "the inputs are fighting each other — no real edge either way."
        icon = "flat"
    return {"tag": tag, "sub": sub, "icon": icon}


NOTABLE_SERIES = [
    ("The 10-year yield", "rate.ust_10y", "%", 2),
    ("The VIX", "vol.vix", "", 2),
    ("Brent", "oil.brent", "$/bbl", 2),
    ("Henry Hub gas", "gas.henry_hub", "$/MMBtu", 2),
    ("The Brent−WTI spread", "derived.brent_wti_spread", "$/bbl", 2),
    ("The HY−IG spread", "derived.hy_ig_spread", "bp", 0),
    ("Singapore's USEP", "power.sg_usep", "S$/MWh", 2),
    ("Singapore's clean spark", "derived.sg_spark", "S$/MWh", 1),
    ("The broad dollar", "fx.usd_broad", "", 2),
]


def _extreme(store, series: str, window: int = 60, min_sessions: int = 10):
    """Where today's print ranks within its trailing window. None if too little
    history to say anything meaningful yet."""
    h = history(store, series).tail(window)
    vals = [float(v) for v in h["value"] if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < min_sessions:
        return None
    lo, hi, cur, n = min(vals), max(vals), vals[-1], len(vals)
    if hi == lo:
        return None
    pct = (cur - lo) / (hi - lo) * 100.0
    return {"pct": pct, "n": n, "cur": cur, "is_max": cur >= hi - 1e-9, "is_min": cur <= lo + 1e-9}


def notable_moves(store, window: int = 60, max_items: int = 3) -> list[str]:
    """'Worth a look today' — series sitting at a genuine multi-session extreme, the
    kind of fact a desk would actually mention out loud. Ranked by how extreme, not
    by which series happens to lead a static list."""
    candidates = []
    for label, series, unit, nd in NOTABLE_SERIES:
        ext = _extreme(store, series, window)
        if ext is None:
            continue
        extremity = abs(ext["pct"] - 50.0)
        if extremity < 38:   # roughly: needs to be in the top/bottom ~12% of the window
            continue
        superlative = "high" if ext["is_max"] else ("low" if ext["is_min"] else
                      ("highest read" if ext["pct"] >= 50 else "lowest read"))
        val = f"{ext['cur']:,.{nd}f}{(' ' + unit) if unit else ''}"
        sentence = f"{label} just printed its {ext['n']}-session {superlative} — {val}."
        candidates.append((extremity, sentence))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in candidates[:max_items]]


# --------------------------------------------------------------------------- #
# Section explainers — each returns what / today / matters.
# --------------------------------------------------------------------------- #
def _rates(store):
    y2, y10 = _v(store, "rate.ust_2y"), _v(store, "rate.ust_10y")
    real10 = _v(store, "rate.real_10y")
    slope = macro.curve_slope_bps(y2, y10) if (y2 is not None and y10 is not None) else math.nan
    d10 = _delta(store, "rate.ust_10y")

    if slope is None or math.isnan(slope):
        shape = "The yield curve can't be read today (data unavailable)."
    elif slope < 0:
        shape = (f"The 2s10s slope is {slope:,.0f}bp — the curve is <b>inverted</b> "
                 f"(short rates above long rates), historically one of the most reliable "
                 f"recession warning signs.")
    elif slope < 50:
        shape = (f"The 2s10s slope is {slope:,.0f}bp — a <b>flat</b> curve, which tends to "
                 f"signal a late-cycle economy where growth and policy are finely balanced.")
    else:
        shape = (f"The 2s10s slope is {slope:,.0f}bp — a <b>positively sloped</b> curve, "
                 f"the normal shape that signals expectations of steady growth ahead.")

    today = (f"The US 10-year yield {_word(d10)} to {_num(y10)}% "
             f"({'+' if (d10 or 0) >= 0 else '−'}{abs((d10 or 0) * 100):,.0f}bp on the day), "
             f"with the 2-year at {_num(y2)}%. {shape} The 10-year <i>real</i> yield "
             f"(after expected inflation) is {_num(real10)}%.")

    return {
        "key": "rates", "title": "Rates & the yield curve",
        "plain": ("Government bond yields are what it costs the US government to borrow over "
                  "2, 10 and 30 years. The <i>shape</i> of that curve — especially the 10-year "
                  "minus the 2-year ('2s10s') — is a closely watched read on the economic cycle."),
        "today": today,
        "matters": ("For energy this is the master dial: the 10-year <b>real</b> yield is the "
                    "discount rate behind every renewable project and long-term power-purchase "
                    "agreement. When real yields rise, capital-heavy solar and wind get more "
                    "expensive to finance — the cost of capital, not panel prices, moves the economics."),
    }


def _dollar(store):
    usd = _v(store, "fx.usd_broad")
    dchg = _delta(store, "fx.usd_broad")
    # USD vs Brent correlation, date-aligned
    ha = history(store, "fx.usd_broad")[["date", "value"]].rename(columns={"value": "a"})
    hb = history(store, "oil.brent")[["date", "value"]].rename(columns={"value": "b"})
    corr = math.nan
    if not ha.empty and not hb.empty:
        m = ha.merge(hb, on="date", how="inner").sort_values("date")
        corr = signals.rolling_corr(m["a"], m["b"], config.CROSS_ASSET_CORR_WINDOW)

    corr_txt = ""
    if not math.isnan(corr):
        corr_txt = (f" The trailing correlation between daily dollar and Brent moves is "
                    f"{corr:+.2f}, the textbook inverse link in action.")

    return {
        "key": "dollar", "title": "The dollar & FX",
        "plain": ("The broad dollar index measures the US dollar against a basket of "
                  "trading-partner currencies. Almost every commodity — oil, gas, metals — "
                  "is priced in dollars, so the dollar's level ripples through the whole complex."),
        "today": (f"The broad dollar index is {_num(usd)} and {_word(dchg)} today. "
                  f"EUR/USD is {_num(_v(store, 'fx.eur_usd'), 4)}, USD/JPY {_num(_v(store, 'fx.usd_jpy'))}."
                  + corr_txt),
        "matters": ("A stronger dollar is a headwind for commodity prices: it makes oil and gas "
                    "more expensive for buyers outside the US, which softens demand. Watching the "
                    "dollar is half of reading where energy prices go next."),
    }


def _risk(store):
    vix = _v(store, "vol.vix")
    hy = _v(store, "credit.hy_oas")
    hy_z = signals.rolling_zscore(history(store, "credit.hy_oas")["value"])
    d2, d10 = _delta(store, "rate.ust_2y"), _delta(store, "rate.ust_10y")
    curve_chg = ((d10 - d2) * 100.0) if (d2 is not None and d10 is not None) else math.nan
    regime, score = macro.risk_regime(vix if vix is not None else math.nan, hy_z,
                                      _delta(store, "fx.usd_broad") or math.nan, curve_chg)
    mood = _mood(regime, 0.0 if (score is None or math.isnan(score)) else score)

    if vix is None:
        vix_txt = "Volatility data is unavailable today."
    elif vix >= config.VIX_STRESS:
        vix_txt = f"The VIX is {_num(vix)} — <b>elevated</b>, signalling market stress."
    elif vix <= config.VIX_CALM:
        vix_txt = f"The VIX is {_num(vix)} — <b>calm</b>, signalling complacent, risk-seeking markets."
    else:
        vix_txt = f"The VIX is {_num(vix)} — a <b>middling</b> level, neither calm nor stressed."

    ig = _v(store, "credit.ig_oas")
    hy_ig = _num(_v(store, "derived.hy_ig_spread"), 0)
    return {
        "key": "risk", "title": "Credit, volatility & risk appetite",
        "plain": ("Credit spreads (the extra yield investors demand to lend to companies rather "
                  "than the government) and the VIX (the market's expectation of stock-market "
                  "swings) together measure the market's appetite for risk."),
        "today": (f"The cross-asset regime reads <b>{mood['tag']}</b> ({regime}). {vix_txt} "
                  f"High-yield credit spreads sit at {_num(hy)}% and investment-grade at {_num(ig)}% "
                  f"— a <b>{hy_ig}bp</b> differential, the market's price for lending to riskier "
                  f"borrowers over safer ones."),
        "matters": ("Risk-off conditions — widening credit spreads and a rising VIX — tend to drag "
                    "commodity-linked and energy equities down alongside everything else, regardless "
                    "of energy's own supply-and-demand picture. It's the macro tide under the boats."),
    }


def _energy(store):
    gas = _v(store, "gas.henry_hub")
    brent = _v(store, "oil.brent")
    ccgt = _v(store, "derived.ccgt_breakeven")
    switch = _v(store, "derived.fuel_switch_carbon")
    gchg, bchg = _delta(store, "gas.henry_hub"), _delta(store, "oil.brent")
    bw = _num(_v(store, "derived.brent_wti_spread"), 2)

    return {
        "key": "energy", "title": "Energy & generation economics",
        "plain": ("Henry Hub is the US natural-gas benchmark; Brent and WTI are the global and US "
                  "crude benchmarks. The <b>CCGT breakeven</b> is the power price at which a gas plant "
                  "just covers its fuel cost — its place in the 'merit order', the cheapest-first "
                  "stack that sets the electricity price."),
        "today": (f"Henry Hub gas is {_num(gas)} $/MMBtu and {_word(gchg)}; Brent is {_num(brent)} "
                  f"$/bbl and {_word(bchg)}; WTI {_num(_v(store, 'oil.wti'))} $/bbl — a Brent−WTI "
                  f"spread of <b>${bw}/bbl</b>. At a standard heat rate, gas implies a power "
                  f"breakeven near <b>{_num(ccgt, 1)} $/MWh</b>."),
        "matters": (f"When gas is cheap, gas plants sit low in the merit order and pull power prices "
                    f"down; when it's dear, coal and gas swap places. The fuel-switching carbon price "
                    f"({_num(switch, 1)} $/t) is the carbon price at which gas would overtake coal in "
                    f"the stack — the number that links climate policy to the day-ahead power market. "
                    f"The Brent−WTI spread, meanwhile, reflects transport and quality differences "
                    f"between the two crude benchmarks — it widens when US supply outpaces pipeline "
                    f"and export capacity to the coast."),
    }


def _bridge(store):
    real10 = _v(store, "rate.real_10y")
    lcoe = _v(store, "derived.solar_lcoe")
    lcoe_up = macro.lcoe_from_real_yield(
        (real10 + 1.0), config.TRANSITION_WACC_PREMIUM, config.LCOE_CAPEX_PER_KW,
        config.LCOE_CAPACITY_FACTOR, config.LCOE_LIFE_YEARS,
        config.LCOE_FIXED_OM_PER_KW_YR) if real10 is not None else math.nan
    delta = (lcoe_up - lcoe) if (lcoe is not None and not math.isnan(lcoe_up)) else math.nan

    return {
        "key": "bridge", "title": "The macro → energy bridge",
        "plain": ("The single idea that ties this whole page together: macro conditions set the "
                  "cost of capital, and the cost of capital sets the price of clean energy."),
        "today": (f"At today's 10-year real yield of {_num(real10)}%, a stylised utility-scale solar "
                  f"build levelises to about <b>{_num(lcoe, 1)} $/MWh</b>. A 1-percentage-point rise in "
                  f"real yields would push that to roughly {_num(lcoe_up, 1)} $/MWh "
                  f"(+{_num(delta, 1)})."),
        "matters": ("This is why an energy trader has to be a macro trader. A move in real yields — "
                    "driven by inflation data, Fed policy, the whole rates complex above — flows "
                    "straight into the economics of every renewable project, often more than the "
                    "weather or the gas price does."),
    }


def _power(store):
    de_p, de_s = _v(store, "power.de_lu"), _v(store, "derived.de_spark")
    sg_p, sg_s = _v(store, "power.sg_usep"), _v(store, "derived.sg_spark")
    sg_d = _v(store, "power.sg_demand")

    parts = []
    if sg_p is not None:
        parts.append(f"Singapore's USEP is <b>S${_num(sg_p)}/MWh</b>"
                     + (f" and system demand {_num(sg_d, 0)} MW" if sg_d is not None else "")
                     + (f", a clean spark spread of about <b>S${_num(sg_s, 1)}/MWh</b> against assumed "
                        f"LNG and the S$45/t carbon tax" if sg_s is not None else ""))
    if de_p is not None:
        parts.append(f"Germany's day-ahead price is €{_num(de_p)}/MWh"
                     + (f", a clean spark spread near <b>€{_num(de_s, 1)}/MWh</b>" if de_s is not None else ""))
    today = ". ".join(p[0].upper() + p[1:] for p in parts) + "." if parts else \
        "Live power data isn't available right now."

    return {
        "key": "power", "title": "Live power & spark spreads",
        "plain": ("A <b>spark spread</b> is a gas plant's gross margin: the electricity price it earns "
                  "minus the cost of the gas (and carbon) it must burn to make that power. Unlike the "
                  "CCGT breakeven above — which is an estimate from gas alone — this uses a <i>live</i> "
                  "wholesale power price, so it's the real-money version of the same idea."),
        "today": today,
        "matters": ("A positive spark spread means gas generation is in the money and gas is likely "
                    "setting the price at the margin; a thin or negative one means cheaper plants — "
                    "renewables, or coal where it exists — are pushing gas down the merit order. For a "
                    "solar-plus-storage desk this is the number that says when it pays to generate or "
                    "discharge into the grid versus hold. Power prices are live; the fuel and carbon "
                    "inputs are clearly-labelled assumptions, since no free daily feed exists for them."),
    }


def _top_mover(store):
    """The single biggest day-over-day move worth naming, or None on a dead-quiet day."""
    defs = [("Brent", "oil.brent", "pct"), ("Henry Hub gas", "gas.henry_hub", "pct"),
            ("the 10Y", "rate.ust_10y", "bp"), ("the dollar", "fx.usd_broad", "pct"),
            ("the VIX", "vol.vix", "pct"), ("USEP", "power.sg_usep", "pct")]
    best = None
    for label, s, kind in defs:
        _, chg, pct = _move(store, s)
        if chg is None or pct is None:
            continue
        if kind == "bp":
            mag = abs(chg * 100)
            if mag < 1:
                continue
            txt = f"{label} {'+' if chg >= 0 else '−'}{mag:.0f}bp"
        else:
            mag = abs(pct)
            if mag < 0.3:
                continue
            arrow = "▲" if pct >= 0 else "▼"
            txt = f"{label} {arrow} {mag:.1f}%"
        # normalize bp and pct onto a roughly comparable "how big a deal" scale
        score = mag if kind == "pct" else mag / 4.0
        if best is None or score > best[0]:
            best = (score, txt)
    return best[1] if best else None


def _move(store, s):
    """Return (last_value, abs_change, pct_change) day-over-day, or (last, None, None)."""
    h = history(store, s)
    if h.empty:
        return None, None, None
    if len(h) < 2:
        return float(h.iloc[-1]["value"]), None, None
    a, b = float(h.iloc[-2]["value"]), float(h.iloc[-1]["value"])
    pct = ((b - a) / a * 100.0) if a else None
    return b, b - a, pct


def whats_changed(store) -> dict:
    """A plain-English 'what moved since the prior session' line for the hero + email.

    Singapore USEP is live daily, so it's always reported; macro series (rates, FX,
    oil, gas) publish with a lag and are flat on weekends, so they're only called out
    when they actually moved — otherwise we say so, which is itself reassuring.
    """
    bits = []

    # USEP — the live daily tell, always shown if present.
    usep, _, upct = _move(store, "power.sg_usep")
    if usep is not None and upct is not None:
        arrow = "▲" if upct >= 0 else "▼"
        bits.append(f"USEP {arrow} {abs(upct):.1f}% to S${usep:,.0f}/MWh")
    elif usep is not None:
        bits.append(f"USEP at S${usep:,.0f}/MWh")

    # Macro movers — only if they meaningfully moved (>=0.3%), biggest first.
    macro_defs = [("Brent", "oil.brent", "pct"), ("gas", "gas.henry_hub", "pct"),
                  ("the 10Y", "rate.ust_10y", "bp"), ("the dollar", "fx.usd_broad", "pct"),
                  ("the VIX", "vol.vix", "pct")]
    movers = []
    for label, s, kind in macro_defs:
        last, chg, pct = _move(store, s)
        if pct is None or chg is None:
            continue
        if kind == "bp":
            if abs(chg * 100) >= 1:
                movers.append((abs(chg * 100), f"{label} {'+' if chg >= 0 else '−'}{abs(chg * 100):.0f}bp"))
        else:
            if abs(pct) >= 0.3:
                arrow = "▲" if pct >= 0 else "▼"
                movers.append((abs(pct), f"{label} {arrow} {abs(pct):.1f}%"))
    movers.sort(reverse=True)
    bits.extend(m[1] for m in movers[:3])

    if len(bits) <= 1:  # only USEP (or nothing) moved
        quiet_pool = ["macro markets little changed since the prior session",
                      "a flat session across the board — nothing chasing here",
                      "rates, FX and energy all sat on their hands overnight"]
        bits.append(_pick(quiet_pool, _day_seed(store, "changed")))

    return {"line": "  ·  ".join(bits)}


GLOSSARY = [
    ("2s10s", "The 10-year Treasury yield minus the 2-year. Positive = normal upward-sloping curve; "
              "negative = 'inverted', a classic recession signal."),
    ("Real yield", "A bond yield after subtracting expected inflation — the true, inflation-adjusted "
                   "cost of money, and the discount rate for long-lived assets."),
    ("Breakeven inflation", "The inflation rate the bond market is pricing in, derived from the gap "
                            "between normal and inflation-protected (TIPS) yields."),
    ("OAS (credit spread)", "Option-adjusted spread: the extra yield over Treasuries that investors "
                            "demand to hold corporate debt. Wider = more fear of defaults."),
    ("VIX", "The market's expected 30-day volatility of the S&P 500 — the 'fear gauge'. Above ~20 is "
            "stressed; below ~15 is calm."),
    ("Merit order", "The stack of power plants ordered cheapest-first. The most expensive plant needed "
                    "to meet demand sets the electricity price for everyone."),
    ("Spark spread", "A gas plant's gross margin: the power price it earns minus the cost of the gas "
                     "(and carbon) it burns to make that power."),
    ("CCGT breakeven", "The power price at which a combined-cycle gas plant exactly covers its fuel "
                       "cost — where it sits in the merit order."),
    ("USEP", "Uniform Singapore Energy Price — the half-hourly wholesale electricity price for "
             "Singapore's gas-dominated grid, the price energy withdrawals settle at."),
    ("Day-ahead price", "The wholesale power price set in an auction the day before delivery, hour by "
                        "hour. ENTSO-E publishes it for each European bidding zone."),
    ("Brent−WTI spread", "The price gap between the two main crude benchmarks, driven by transport "
                         "costs, quality, and pipeline/export capacity — a classic relative-value trade."),
    ("HY−IG spread", "The gap between high-yield and investment-grade credit spreads — how much extra "
                     "the market demands for the riskiest borrowers specifically, isolated from the "
                     "general level of rates."),
    ("Yield curve inversion", "When a shorter-maturity bond yields more than a longer one (e.g. 2Y "
                              "above 10Y). Unusual, and historically one of the more reliable signals "
                              "that a recession may lie ahead."),
    ("LCOE", "Levelised cost of energy: the all-in lifetime cost of a power project per MWh, dominated "
             "by upfront capital and therefore very sensitive to interest rates."),
    ("HDD / CDD", "Heating- and cooling-degree-days: how far temperature sits below/above a comfort "
                  "baseline — a direct proxy for energy demand."),
]


def _headline(store):
    """One-line lead for the top of the page and the email subject. Leads with
    whichever is most interesting today — a genuine multi-session extreme, a big
    move, or (on a quiet day) says so — rather than reciting the same three numbers
    every morning. Phrasing rotates on a per-day seed so it stays fresh."""
    vix = _v(store, "vol.vix")
    y2, y10 = _v(store, "rate.ust_2y"), _v(store, "rate.ust_10y")
    slope = macro.curve_slope_bps(y2, y10) if (y2 is not None and y10 is not None) else math.nan
    hy_z = signals.rolling_zscore(history(store, "credit.hy_oas")["value"])
    d2, d10 = _delta(store, "rate.ust_2y"), _delta(store, "rate.ust_10y")
    curve_chg = ((d10 - d2) * 100.0) if (d2 is not None and d10 is not None) else math.nan
    regime, score = macro.risk_regime(vix if vix is not None else math.nan, hy_z,
                                      _delta(store, "fx.usd_broad") or math.nan, curve_chg)
    mood = _mood(regime, 0.0 if (score is None or math.isnan(score)) else score)
    inv = (not math.isnan(slope)) and slope < 0
    seed = _day_seed(store, "headline")

    extremes = notable_moves(store, max_items=1)
    mover = _top_mover(store)
    inv_clause = " — and the curve's inverted" if inv else ""

    if extremes:
        pool = [
            f"{extremes[0]} That's the story today; the book reads <b>{mood['tag']}</b>.",
            f"Mark this one — {extremes[0]} Regime stays <b>{mood['tag']}</b>{inv_clause}.",
            f"{extremes[0]} Everything else is secondary today.",
        ]
        return _pick(pool, seed)

    if mover:
        pool = [
            f"{mover} is doing the talking — book reads <b>{mood['tag']}</b>{inv_clause}.",
            f"The story today is {mover}. Regime: <b>{mood['tag']}</b>.",
            f"{mover}, and not much else moved. Call it <b>{mood['tag']}</b>{inv_clause}.",
        ]
        return _pick(pool, seed)

    quiet = [
        f"Quiet tape — nothing loud enough to trade on, book stays <b>{mood['tag']}</b>{inv_clause}.",
        f"Not much doing today. Regime reads <b>{mood['tag']}</b>{inv_clause}.",
        f"A grinder of a session, no real prints worth chasing. <b>{mood['tag']}</b> underneath it all.",
    ]
    return _pick(quiet, seed)


def build_explainers(store) -> dict:
    vix = _v(store, "vol.vix")
    hy_z = signals.rolling_zscore(history(store, "credit.hy_oas")["value"])
    d2, d10 = _delta(store, "rate.ust_2y"), _delta(store, "rate.ust_10y")
    curve_chg = ((d10 - d2) * 100.0) if (d2 is not None and d10 is not None) else math.nan
    regime, score = macro.risk_regime(vix if vix is not None else math.nan, hy_z,
                                      _delta(store, "fx.usd_broad") or math.nan, curve_chg)
    mood = _mood(regime, 0.0 if (score is None or math.isnan(score)) else score)
    return {
        "headline": _headline(store),
        "changed": whats_changed(store)["line"],
        "mood": mood,
        "notable": notable_moves(store),
        "sections": [_rates(store), _dollar(store), _risk(store), _energy(store), _power(store), _bridge(store)],
        "glossary": [{"term": t, "def": d} for t, d in GLOSSARY],
    }
