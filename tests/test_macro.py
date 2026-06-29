"""
Tests for the macro & cross-asset analytics. Pure functions, run in CI on every push
so the rates/curve/LCOE maths and the regime logic can't silently regress.
"""
import math

import pandas as pd

from analytics.macro import (
    curve_slope_bps, is_inverted, risk_regime,
    capital_recovery_factor, renewable_lcoe, lcoe_from_real_yield,
)
from analytics.signals import rolling_corr


def test_curve_slope_and_inversion():
    assert curve_slope_bps(3.9, 4.3) == pytest_approx(40.0)
    assert is_inverted(curve_slope_bps(4.6, 4.3)) is True     # 2y above 10y -> inverted
    assert is_inverted(curve_slope_bps(3.9, 4.3)) is False


def test_capital_recovery_factor_known_value():
    # CRF(7%, 25y) ~ 0.085808
    assert math.isclose(capital_recovery_factor(0.07, 25), 0.085808, rel_tol=1e-4)
    # Zero-rate degenerates to straight-line 1/n
    assert math.isclose(capital_recovery_factor(0.0, 20), 0.05, rel_tol=1e-9)


def test_renewable_lcoe_worked_example():
    # capex 1000/kW, CF 0.20, r 7%, 25y, no O&M:
    #   annual capex = 1000 * 0.085808 = 85.808 ; annual MWh/kW = 0.2*8760/1000 = 1.752
    #   LCOE = 85.808 / 1.752 ~ 48.98 $/MWh
    lcoe = renewable_lcoe(1000.0, 0.20, 0.07, 25, 0.0)
    assert math.isclose(lcoe, 48.98, rel_tol=2e-3)


def test_lcoe_rises_with_rates():
    lo = renewable_lcoe(1000.0, 0.16, 0.05, 25, 15.0)
    hi = renewable_lcoe(1000.0, 0.16, 0.07, 25, 15.0)
    assert hi > lo    # higher discount rate -> higher levelised cost


def test_lcoe_from_real_yield_matches_direct():
    direct = renewable_lcoe(1000.0, 0.16, 0.02 + 0.045, 25, 15.0)
    wrapped = lcoe_from_real_yield(2.0, 0.045, 1000.0, 0.16, 25, 15.0)
    assert math.isclose(direct, wrapped, rel_tol=1e-9)


def test_risk_regime_classification():
    off, _ = risk_regime(vix=30, hy_oas_z=2.0, dxy_chg=0.5, curve_chg_bps=-5)
    on, _ = risk_regime(vix=12, hy_oas_z=-2.0, dxy_chg=-0.3, curve_chg_bps=5)
    mixed, _ = risk_regime(vix=17, hy_oas_z=0.0, dxy_chg=0.0, curve_chg_bps=0.0)
    unknown, score = risk_regime(vix=math.nan, hy_oas_z=math.nan,
                                 dxy_chg=math.nan, curve_chg_bps=math.nan)
    assert off == "risk-off"
    assert on == "risk-on"
    assert mixed == "neutral / mixed"
    assert unknown == "unknown" and math.isnan(score)


def test_rolling_corr_perfect_and_short():
    a = pd.Series([0, 1, 3, 6, 10, 15, 21, 28, 36, 45])   # diffs 1,2,3,...
    b = a * 3                                              # diffs scaled -> corr +1
    assert math.isclose(rolling_corr(a, b, 30), 1.0, rel_tol=1e-6)
    assert math.isclose(rolling_corr(a, -2 * a, 30), -1.0, rel_tol=1e-6)
    assert math.isnan(rolling_corr(pd.Series([1, 2, 3, 4, 5]), pd.Series([2, 4, 6, 8, 10]), 30))


# Tiny local approx helper so this file needs no pytest plugin features.
def pytest_approx(x, tol=1e-9):
    class _A:
        def __eq__(self, other):
            return abs(other - x) <= tol
    return _A()
