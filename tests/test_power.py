"""Tests for the live power module: spark-spread math (both conventions) and the
ENTSO-E day-ahead XML parser."""
import math

import config
from analytics.spreads import clean_spark_spread
from ingest.entsoe import _parse_prices


def test_german_spark_european_convention():
    # power 95 EUR/MWh, gas 32 EUR/MWh-th, heat rate 2.0, carbon 70 EUR/t, ef 0.37
    s = clean_spark_spread(95.0, config.ASSUMED_TTF_EUR_PER_MWH,
                           1.0 / config.SPARK_EFFICIENCY_EU,
                           config.ASSUMED_EUA_EUR_PER_TONNE, config.EF_GAS_TONNE_PER_MWH)
    assert math.isclose(s, 95.0 - 32.0 * 2.0 - 70.0 * 0.37, rel_tol=1e-9)


def test_singapore_spark_native_sgd():
    # USEP 170, SG gas 16 SGD/MMBtu, heat rate 7.0, carbon 45 SGD/t, ef 0.37
    s = clean_spark_spread(170.0, config.ASSUMED_SG_GAS_SGD_PER_MMBTU,
                           config.HEAT_RATE_CCGT_SG,
                           config.ASSUMED_SG_CARBON_SGD_PER_TONNE, config.EF_GAS_TONNE_PER_MWH)
    assert math.isclose(s, 170.0 - 16.0 * 7.0 - 45.0 * 0.37, rel_tol=1e-9)
    assert s > 0  # Singapore gas plants in the money at these levels


def test_singapore_carbon_is_2026_rate():
    assert config.ASSUMED_SG_CARBON_SGD_PER_TONNE == 45.0


def test_entsoe_parser_extracts_prices():
    xml = ("<Publication_MarketDocument><TimeSeries><Period>"
           "<Point><position>1</position><price.amount>42.50</price.amount></Point>"
           "<Point><position>2</position><price.amount>55.10</price.amount></Point>"
           "</Period></TimeSeries></Publication_MarketDocument>")
    prices = _parse_prices(xml)
    assert prices == [42.50, 55.10]


def test_entsoe_parser_empty_on_no_data():
    assert _parse_prices("<Acknowledgement_MarketDocument/>") == []
