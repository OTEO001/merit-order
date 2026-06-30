"""
Tests for the explanation engine + email builder. These guard two things:
  1. the structure the dashboard and email depend on is always present, and
  2. neither crashes on a sparse/empty store (early days, or every feed down).
"""
import pandas as pd

from ingest.base import COLUMNS
from briefing.explain import build_explainers
from briefing.email_digest import build_email


def _store(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


def _series(name, values, unit="x"):
    return [{"date": f"2026-06-{10+i:02d}", "series": name, "value": float(v),
             "unit": unit, "source": "test", "as_of": f"2026-06-{10+i:02d}"}
            for i, v in enumerate(values)]


def test_explainers_structure_on_populated_store():
    rows = (_series("rate.ust_2y", [3.8, 3.9]) + _series("rate.ust_10y", [4.2, 4.3])
            + _series("rate.real_10y", [1.9, 1.95]) + _series("vol.vix", [15, 16])
            + _series("credit.hy_oas", [3.2, 3.3]) + _series("fx.usd_broad", [119, 120])
            + _series("oil.brent", [77, 78]) + _series("gas.henry_hub", [3.4, 3.5]))
    ex = build_explainers(_store(rows))
    assert "headline" in ex and ex["headline"]
    assert len(ex["sections"]) == 6
    for s in ex["sections"]:
        assert {"key", "title", "plain", "today", "matters"} <= set(s)
    assert len(ex["glossary"]) >= 8


def test_explainers_do_not_crash_on_empty_store():
    ex = build_explainers(_store([]))
    assert len(ex["sections"]) == 6          # still structured, just with "—" values
    assert isinstance(ex["headline"], str)


def test_email_builds_subject_and_html():
    rows = _series("rate.ust_10y", [4.2, 4.3]) + _series("oil.brent", [77, 78])
    subject, html = build_email(_store(rows))
    assert subject.startswith("Merit Order")
    assert "<html" in html.lower() and "Why it matters" in html
