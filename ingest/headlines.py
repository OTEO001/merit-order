"""
Energy headlines — the "big events" layer, in the form of real published headlines
rather than just price moves.

Deliberately sourced from official/institutional RSS feeds only (see
config.HEADLINES_FEEDS) rather than scraped news sites or unofficial mirrors: this
keeps the module on solid legal ground and off fragile, ToS-risky scrapers. Only the
headline, publish date, source, and a link are kept — never article body text, which
is exactly how RSS aggregation is meant to work and keeps this comfortably inside
copyright norms (facts and titles aren't protected; reproducing article prose would be).

Best-effort and self-contained, matching fetch_calendar(): any failure — a feed
timing out, a malformed entry — is swallowed and simply narrows the results, never
breaks the daily run. Writes config.HEADLINES_JSON as a side effect.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import config
from ingest.base import http_get_text


def _strip_tags(s: str) -> str:
    """RSS titles occasionally carry HTML entities/tags; keep this to plain text."""
    s = re.sub(r"<[^>]+>", "", s or "")
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&#39;", "'").replace("&quot;", '"'))
    return s.strip()


def _parse_rss_items(xml: str, source_name: str, limit: int) -> list[dict]:
    """Minimal, dependency-free RSS 2.0 <item> parser (title/link/pubDate)."""
    items = []
    for block in re.findall(r"<item\b.*?</item>", xml, flags=re.S | re.I)[:limit]:
        title_m = re.search(r"<title>(.*?)</title>", block, flags=re.S | re.I)
        link_m = re.search(r"<link>(.*?)</link>", block, flags=re.S | re.I)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, flags=re.S | re.I)
        title = _strip_tags(title_m.group(1)) if title_m else ""
        link = _strip_tags(link_m.group(1)) if link_m else ""
        if not title or not link:
            continue
        published = ""
        if date_m:
            raw = _strip_tags(date_m.group(1))
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
                try:
                    published = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if not published:
                published = raw[:16]  # keep something readable rather than drop it
        items.append({"title": title, "link": link, "source": source_name, "published": published})
    return items


def fetch_headlines() -> list[dict]:
    """
    Latest energy headlines from the configured official feeds, newest first.
    Best-effort per feed: one dead feed doesn't take down the others. Always writes
    config.HEADLINES_JSON (possibly []) so the dashboard/email can read it directly.
    """
    headlines: list[dict] = []
    if config.ENABLE_HEADLINES:
        for feed in config.HEADLINES_FEEDS:
            try:
                xml = http_get_text(feed["url"])
                headlines.extend(_parse_rss_items(xml, feed["name"], config.HEADLINES_MAX))
            except Exception:
                continue   # one bad feed never blanks the others

        def _sort_key(h):
            return h.get("published") or "0000-00-00"
        headlines.sort(key=_sort_key, reverse=True)
        headlines = headlines[: config.HEADLINES_MAX]

    config.HEADLINES_JSON.parent.mkdir(parents=True, exist_ok=True)
    config.HEADLINES_JSON.write_text(json.dumps(headlines), encoding="utf-8")
    return headlines
