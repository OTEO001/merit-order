"""Tests for the energy-headlines module: RSS parsing, entity decoding, and the
never-break-the-run resilience pattern shared with fetch_calendar()."""
from unittest.mock import patch

from ingest.headlines import _parse_rss_items, _strip_tags, fetch_headlines


SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Today in Energy</title>
<item>
<title>UAE&#39;s exit from OPEC+ reduced the group&#39;s share of production</title>
<link>https://www.eia.gov/todayinenergy/detail.php?id=1</link>
<pubDate>Mon, 29 Jun 2026 05:00:00 -0400</pubDate>
</item>
<item>
<title>U.S. commercial crude oil inventories decreased in June</title>
<link>https://www.eia.gov/todayinenergy/detail.php?id=2</link>
<pubDate>Wed, 01 Jul 2026 05:00:00 -0400</pubDate>
</item>
</channel></rss>"""


def test_strip_tags_decodes_entities():
    assert _strip_tags("Gas &amp; oil &#39;prices&#39;") == "Gas & oil 'prices'"


def test_parse_rss_items_extracts_title_link_date():
    items = _parse_rss_items(SAMPLE_RSS, "EIA — Today in Energy", 6)
    assert len(items) == 2
    assert items[0]["title"] == "UAE's exit from OPEC+ reduced the group's share of production"
    assert items[0]["link"].startswith("https://www.eia.gov/")
    assert items[0]["published"] == "2026-06-29"
    assert items[0]["source"] == "EIA — Today in Energy"


def test_parse_rss_items_respects_limit():
    items = _parse_rss_items(SAMPLE_RSS, "Test", limit=1)
    assert len(items) == 1


def test_parse_rss_items_skips_malformed_entries():
    xml = "<rss><channel><item><title>No link here</title></item></channel></rss>"
    assert _parse_rss_items(xml, "Test", 6) == []


def test_fetch_headlines_never_raises_on_network_failure(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "HEADLINES_JSON", tmp_path / "_headlines.json")
    with patch("ingest.headlines.http_get_text", side_effect=RuntimeError("boom")):
        result = fetch_headlines()
    assert result == []
    assert config.HEADLINES_JSON.exists()


def test_fetch_headlines_disabled_returns_empty(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "HEADLINES_JSON", tmp_path / "_headlines.json")
    monkeypatch.setattr(config, "ENABLE_HEADLINES", False)
    assert fetch_headlines() == []
