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

import math

import config
from analytics import macro, signals
from store import history, latest_value


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

    if vix is None:
        vix_txt = "Volatility data is unavailable today."
    elif vix >= config.VIX_STRESS:
        vix_txt = f"The VIX is {_num(vix)} — <b>elevated</b>, signalling market stress."
    elif vix <= config.VIX_CALM:
        vix_txt = f"The VIX is {_num(vix)} — <b>calm</b>, signalling complacent, risk-seeking markets."
    else:
        vix_txt = f"The VIX is {_num(vix)} — a <b>middling</b> level, neither calm nor stressed."

    return {
        "key": "risk", "title": "Credit, volatility & risk appetite",
        "plain": ("Credit spreads (the extra yield investors demand to lend to companies rather "
                  "than the government) and the VIX (the market's expectation of stock-market "
                  "swings) together measure the market's appetite for risk."),
        "today": (f"The cross-asset regime reads <b>{regime}</b>. {vix_txt} "
                  f"High-yield credit spreads sit at {_num(hy)}% and investment-grade at "
                  f"{_num(_v(store, 'credit.ig_oas'))}%."),
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

    return {
        "key": "energy", "title": "Energy & generation economics",
        "plain": ("Henry Hub is the US natural-gas benchmark; Brent and WTI are the global and US "
                  "crude benchmarks. The <b>CCGT breakeven</b> is the power price at which a gas plant "
                  "just covers its fuel cost — its place in the 'merit order', the cheapest-first "
                  "stack that sets the electricity price."),
        "today": (f"Henry Hub gas is {_num(gas)} $/MMBtu and {_word(gchg)}; Brent is {_num(brent)} "
                  f"$/bbl and {_word(bchg)}; WTI {_num(_v(store, 'oil.wti'))} $/bbl. At a standard "
                  f"heat rate, gas implies a power breakeven near <b>{_num(ccgt, 1)} $/MWh</b>."),
        "matters": (f"When gas is cheap, gas plants sit low in the merit order and pull power prices "
                    f"down; when it's dear, coal and gas swap places. The fuel-switching carbon price "
                    f"({_num(switch, 1)} $/t) is the carbon price at which gas would overtake coal in "
                    f"the stack — the number that links climate policy to the day-ahead power market."),
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
    ("LCOE", "Levelised cost of energy: the all-in lifetime cost of a power project per MWh, dominated "
             "by upfront capital and therefore very sensitive to interest rates."),
    ("HDD / CDD", "Heating- and cooling-degree-days: how far temperature sits below/above a comfort "
                  "baseline — a direct proxy for energy demand."),
]


def _headline(store):
    """One-line synthesis for the top of the page and the email subject."""
    vix = _v(store, "vol.vix")
    y2, y10 = _v(store, "rate.ust_2y"), _v(store, "rate.ust_10y")
    slope = macro.curve_slope_bps(y2, y10) if (y2 is not None and y10 is not None) else math.nan
    hy_z = signals.rolling_zscore(history(store, "credit.hy_oas")["value"])
    d2, d10 = _delta(store, "rate.ust_2y"), _delta(store, "rate.ust_10y")
    curve_chg = ((d10 - d2) * 100.0) if (d2 is not None and d10 is not None) else math.nan
    regime, _ = macro.risk_regime(vix if vix is not None else math.nan, hy_z,
                                  _delta(store, "fx.usd_broad") or math.nan, curve_chg)
    inv = (not math.isnan(slope)) and slope < 0
    bits = [f"Markets read <b>{regime}</b>"]
    if y10 is not None:
        bits.append(f"the 10-year at {_num(y10)}%{' with an inverted curve' if inv else ''}")
    brent = _v(store, "oil.brent")
    if brent is not None:
        bits.append(f"Brent near ${_num(brent, 0)}")
    return ", ".join(bits) + "."


def build_explainers(store) -> dict:
    return {
        "headline": _headline(store),
        "sections": [_rates(store), _dollar(store), _risk(store), _energy(store), _bridge(store)],
        "glossary": [{"term": t, "def": d} for t, d in GLOSSARY],
    }
