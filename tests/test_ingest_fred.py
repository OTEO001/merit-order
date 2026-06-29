"""
Ingestion-parsing tests for the FRED source. These feed the *real* FRED response
shapes (observations with "." missing values; the releases/dates calendar) through
the parsing logic with the network monkeypatched out — so the production parsing is
proven correct here, in CI, without hitting the API.
"""
import json
from datetime import date, timedelta

import ingest.fred as fred
import config


def test_fetch_one_parses_observations(monkeypatch):
    sample = {"observations": [
        {"date": "2026-06-24", "value": "4.25"},
        {"date": "2026-06-25", "value": "."},     # FRED's missing-value marker
        {"date": "2026-06-26", "value": "4.30"},
    ]}
    monkeypatch.setattr(fred, "http_get_json", lambda *a, **k: sample)
    df = fred._fetch_one("DGS10")
    assert list(df["value"]) == [4.25, 4.30]       # "." row dropped, floats coerced
    assert list(df["date"]) == ["2026-06-24", "2026-06-26"]


def test_calendar_filters_keywords_and_window(monkeypatch, tmp_path):
    today = date.today()
    d_in = (today + timedelta(days=3)).isoformat()      # in-window, keyword match
    d_far = (today + timedelta(days=60)).isoformat()    # out of window
    sample = {"release_dates": [
        {"release_id": 10, "release_name": "Consumer Price Index", "date": d_in},
        {"release_id": 99, "release_name": "Some Obscure Regional Survey", "date": d_in},
        {"release_id": 53, "release_name": "Gross Domestic Product", "date": d_far},
    ]}
    monkeypatch.setattr(fred, "http_get_json", lambda *a, **k: sample)
    monkeypatch.setattr(config, "FRED_API_KEY", "test-key")
    monkeypatch.setattr(config, "ENABLE_FRED", True)
    monkeypatch.setattr(config, "CALENDAR_JSON", tmp_path / "_calendar.json")

    events = fred.fetch_calendar()
    names = [e["name"] for e in events]
    assert "Consumer Price Index" in names          # kept: keyword + in window
    assert "Some Obscure Regional Survey" not in names   # dropped: no keyword
    assert "Gross Domestic Product" not in names    # dropped: outside the window
    # and it persisted the JSON the briefing reads
    assert json.loads((tmp_path / "_calendar.json").read_text())[0]["name"] == "Consumer Price Index"


def test_fetch_fred_no_key_is_empty(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "")
    # safe_source wraps fetch_fred -> returns a result with an empty frame, never raises
    result = fred.fetch_fred()
    assert result.df.empty
