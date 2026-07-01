"""Tests for the new visual/analytics additions: yield curve snapshot, risk gauge,
90-day range context, and the Brent-WTI / HY-IG relative-value spreads."""
import pandas as pd

from ingest.base import COLUMNS
from dashboard.build import _yield_curve_chart, _risk_gauge, _range_bar


def _store(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


def _series(name, values, unit="x", start="2026-05-01"):
    dates = pd.date_range(start, periods=len(values)).strftime("%Y-%m-%d")
    return [{"date": d, "series": name, "value": float(v), "unit": unit,
             "source": "test", "as_of": d} for d, v in zip(dates, values)]


def test_yield_curve_chart_structure():
    rows = (_series("rate.ust_3m", [4.3] * 30) + _series("rate.ust_2y", [3.8] * 30)
            + _series("rate.ust_5y", [4.0] * 30) + _series("rate.ust_10y", [4.2] * 30)
            + _series("rate.ust_30y", [4.5] * 30))
    yc = _yield_curve_chart(_store(rows))
    assert yc["title"] == "US Treasury curve"
    assert "html" in yc and len(yc["html"]) > 100
    assert yc["prior_date"] is not None


def test_yield_curve_inversion_flag():
    rows = _series("rate.ust_2y", [5.0]) + _series("rate.ust_10y", [4.0])
    yc = _yield_curve_chart(_store(rows))
    assert yc["inverted"] is True


def test_yield_curve_handles_empty_store():
    yc = _yield_curve_chart(_store([]))
    assert yc["title"] == "US Treasury curve"
    assert yc["inverted"] is None


def test_risk_gauge_structure_and_bounds():
    rows = (_series("vol.vix", [25.0] * 95) + _series("credit.hy_oas", [4.5] * 95)
            + _series("fx.usd_broad", [120, 121]) + _series("rate.ust_2y", [3.8, 3.9])
            + _series("rate.ust_10y", [4.2, 4.1]))
    rg = _risk_gauge(_store(rows))
    assert rg["label"] in ("risk-on", "risk-off", "neutral / mixed", "unknown")
    assert -3.0 <= rg["score"] <= 3.0
    assert "html" in rg and len(rg["html"]) > 100


def test_risk_gauge_handles_empty_store():
    rg = _risk_gauge(_store([]))
    assert rg["label"] == "unknown"


def test_range_bar_context():
    rb = _range_bar(_store(_series("vol.vix", [10, 12, 14, 16, 18, 20])), "vol.vix", 1)
    assert rb["lo"] == "10.0" and rb["hi"] == "20.0"
    assert rb["pct"] == 100.0  # last value is the max


def test_range_bar_none_on_insufficient_history():
    assert _range_bar(_store(_series("vol.vix", [15, 16])), "vol.vix") is None
