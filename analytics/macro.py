"""
Macro & cross-asset analytics — pure, NaN-safe functions. The macro analogue of
spreads.py: the numbers a cross-asset desk reasons about, computed from first
principles, plus the bridges that connect macro conditions to energy P&L and
renewable-transition economics.
"""
from __future__ import annotations

import math


def _nan(*vals) -> bool:
    return any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals)


# --------------------------------------------------------------------------- #
# Rates / curve
# --------------------------------------------------------------------------- #
def curve_slope_bps(short_yield: float, long_yield: float) -> float:
    """Curve slope in basis points (long minus short). Negative = inverted."""
    if _nan(short_yield, long_yield):
        return math.nan
    return (long_yield - short_yield) * 100.0


def is_inverted(slope_bps: float) -> bool:
    return (slope_bps is not None) and (not math.isnan(slope_bps)) and slope_bps < 0


# --------------------------------------------------------------------------- #
# Risk regime — a transparent, rules-based tally. Each gauge votes risk-on (-1)
# or risk-off (+1); votes are summed and mapped to a label. No black box.
# --------------------------------------------------------------------------- #
def risk_regime(vix: float, hy_oas_z: float, dxy_chg: float,
                curve_chg_bps: float) -> tuple[str, float]:
    """
    Returns (label, score). Inputs:
      vix            — VIX level
      hy_oas_z       — z-score of high-yield credit spread (widening => stress)
      dxy_chg        — day/day change in the broad dollar (bid => mild haven)
      curve_chg_bps  — day/day change in 2s10s slope (flattening => late-cycle)
    """
    import config
    votes = 0.0
    n = 0

    if not _nan(vix):
        n += 1
        if vix >= config.VIX_STRESS:
            votes += 1
        elif vix <= config.VIX_CALM:
            votes -= 1

    if not _nan(hy_oas_z):
        n += 1
        if hy_oas_z >= config.CREDIT_Z_STRESS:
            votes += 1
        elif hy_oas_z <= -config.CREDIT_Z_STRESS:
            votes -= 1

    if not _nan(dxy_chg):
        n += 1
        votes += 0.5 if dxy_chg > 0 else (-0.5 if dxy_chg < 0 else 0.0)

    if not _nan(curve_chg_bps):
        n += 1
        votes += 0.5 if curve_chg_bps < 0 else (-0.5 if curve_chg_bps > 0 else 0.0)

    if n == 0:
        return ("unknown", math.nan)
    if votes >= config.REGIME_RISKOFF_AT:
        return ("risk-off", votes)
    if votes <= config.REGIME_RISKON_AT:
        return ("risk-on", votes)
    return ("neutral / mixed", votes)


# --------------------------------------------------------------------------- #
# Transition-finance bridge: real yields -> renewable LCOE.
# Higher real yields raise the discount rate, which raises the annualised cost of
# capital-heavy renewables via the capital-recovery factor (CRF). This is the exact
# project-finance algebra (CRF / LCOE) applied to a live macro input.
# --------------------------------------------------------------------------- #
def capital_recovery_factor(rate: float, years: int) -> float:
    """CRF = r(1+r)^n / ((1+r)^n - 1). The annuity factor that levelises capex."""
    if _nan(rate) or years <= 0:
        return math.nan
    if rate == 0:
        return 1.0 / years
    g = (1.0 + rate) ** years
    return rate * g / (g - 1.0)


def renewable_lcoe(capex_per_kw: float, capacity_factor: float, discount_rate: float,
                   life_years: int, fixed_om_per_kw_yr: float = 0.0) -> float:
    """
    Levelised cost of energy ($/MWh) for a capex-driven renewable asset:
        LCOE = (capex * CRF + fixed_O&M_per_kW_yr) / (annual MWh per kW)
    where annual MWh per kW = capacity_factor * 8760 / 1000.
    """
    if _nan(capex_per_kw, capacity_factor, discount_rate):
        return math.nan
    crf = capital_recovery_factor(discount_rate, life_years)
    if math.isnan(crf):
        return math.nan
    annual_cost_per_kw = capex_per_kw * crf + (fixed_om_per_kw_yr or 0.0)
    annual_mwh_per_kw = capacity_factor * 8760.0 / 1000.0
    if annual_mwh_per_kw == 0:
        return math.nan
    return annual_cost_per_kw / annual_mwh_per_kw


def lcoe_from_real_yield(real_yield_pct: float, wacc_premium: float,
                         capex_per_kw: float, capacity_factor: float,
                         life_years: int, fixed_om_per_kw_yr: float = 0.0) -> float:
    """Convenience wrapper: discount rate = real_yield + WACC premium, then LCOE."""
    if _nan(real_yield_pct):
        return math.nan
    discount_rate = real_yield_pct / 100.0 + (wacc_premium or 0.0)
    return renewable_lcoe(capex_per_kw, capacity_factor, discount_rate,
                          life_years, fixed_om_per_kw_yr)
