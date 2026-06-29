"""
Pure-function tests for the analytics core. These run in CI on every push, so a refactor
can never silently break the numbers the desk note quotes.
"""
import math

from analytics.spreads import (
    generation_cost, clean_spark_spread, clean_dark_spread, fuel_switching_price,
)
from analytics.signals import wind_power_proxy, solar_proxy


def test_clean_spark_spread_worked_example():
    # power 120, gas 12, heat rate 7.0, carbon 50, emissions 0.37 -> 17.50
    assert clean_spark_spread(120, 12, 7.0, 50, 0.37) == 17.5


def test_generation_cost_components():
    # fuel 12*7 = 84 ; carbon 50*0.37 = 18.5 ; total 102.5
    assert generation_cost(12, 7.0, 50, 0.37) == 102.5


def test_dark_spread_basic():
    # power 100, coal 3, heat rate 9.5, no carbon -> 100 - 28.5 = 71.5
    assert clean_dark_spread(100, 3, 9.5, 0, 0.85) == 71.5


def test_fuel_switching_price_formula():
    # C* = (gas*hr_g - coal*hr_c) / (ef_c - ef_g)
    gas, coal, hrg, hrc, efg, efc = 12, 3, 7.0, 9.5, 0.37, 0.85
    expected = (gas * hrg - coal * hrc) / (efc - efg)
    assert math.isclose(fuel_switching_price(gas, coal, hrg, hrc, efg, efc), expected)


def test_nan_safety():
    assert math.isnan(clean_spark_spread(None, 12, 7.0))
    assert math.isnan(generation_cost(float("nan"), 7.0))


def test_wind_proxy_band():
    assert wind_power_proxy(2.0) == 0.0      # below cut-in
    assert wind_power_proxy(12.0) == 1.0     # at rated
    assert wind_power_proxy(30.0) == 0.0     # above cut-out
    assert 0.0 < wind_power_proxy(7.0) < 1.0  # cubic ramp region


def test_solar_proxy_clamped():
    assert solar_proxy(0) == 0.0
    assert solar_proxy(8000) == 1.0          # clamped to 1
    assert 0.0 < solar_proxy(400) < 1.0
