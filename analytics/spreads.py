"""
Spread analytics — pure, NaN-safe functions. These are the numbers a desk quotes.

Unit convention (US): power in $/MWh, gas/coal in $/MMBtu, heat rate in MMBtu/MWh,
carbon in $/tonne, emissions factor in tonnes/MWh. For the European convention pass a
gas price in $/MWh-thermal and a heat rate of ~2.0 (MWh-th per MWh-e) — the algebra is
identical because (fuel price x heat rate) is always $/MWh-electric.
"""
from __future__ import annotations

import math


def _nan_safe(*vals) -> bool:
    return any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals)


def generation_cost(gas: float, heat_rate: float,
                    carbon: float = 0.0, ef: float = 0.37) -> float:
    """
    Short-run marginal cost of a gas plant ($/MWh) — i.e. the breakeven power price
    below which it is uneconomic to run. Computable with only a gas price, so it works
    on day one with the free EIA backbone before any power feed is wired.
    """
    if _nan_safe(gas, heat_rate):
        return math.nan
    carbon = 0.0 if carbon is None else carbon
    return gas * heat_rate + carbon * ef


def clean_spark_spread(power: float, gas: float, heat_rate: float,
                       carbon: float = 0.0, ef_gas: float = 0.37) -> float:
    """Gas-plant generation margin: power price minus fuel and carbon cost."""
    if _nan_safe(power, gas, heat_rate):
        return math.nan
    return power - generation_cost(gas, heat_rate, carbon, ef_gas)


def clean_dark_spread(power: float, coal: float, heat_rate_coal: float,
                      carbon: float = 0.0, ef_coal: float = 0.85) -> float:
    """Coal-plant generation margin."""
    if _nan_safe(power, coal, heat_rate_coal):
        return math.nan
    return power - generation_cost(coal, heat_rate_coal, carbon, ef_coal)


def fuel_switching_price(gas: float, coal: float,
                         hr_gas: float, hr_coal: float,
                         ef_gas: float = 0.37, ef_coal: float = 0.85) -> float:
    """
    The carbon price ($/tonne) at which clean spark spread == clean dark spread, i.e.
    where gas and coal are equally economic. Above it, the merit order flips to gas.

    Setting the two spreads equal and cancelling the (common) power price:
        C* = (gas*hr_gas - coal*hr_coal) / (ef_coal - ef_gas)

    Note it needs no power price and no carbon input — a genuinely useful read you can
    publish from gas + a coal reference alone.
    """
    if _nan_safe(gas, coal, hr_gas, hr_coal):
        return math.nan
    denom = ef_coal - ef_gas
    if denom == 0:
        return math.nan
    return (gas * hr_gas - coal * hr_coal) / denom
