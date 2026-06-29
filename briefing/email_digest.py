"""
Daily email digest — a premium, inline-styled HTML email built from the same
explanation engine the dashboard uses, so the morning note that lands in your inbox
teaches the markets, not just lists numbers.

Sending is via SMTP (Gmail address + App Password). Everything is gated on config:
if EMAIL_USER / EMAIL_PASS aren't set, send_digest() is a no-op and the pipeline
continues normally.
"""
from __future__ import annotations

import math
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import config
from briefing.explain import build_explainers
from store import history, latest_value

# palette (kept readable on the light email canvas most clients prefer)
INK, SUB, FAINT = "#0E1320", "#5A6473", "#9AA4B2"
ACCENT, POS, NEG = "#0E7C66", "#0E7C66", "#C0392B"
LINE, CARD, CANVAS = "#E6E9EF", "#FFFFFF", "#F4F6F9"


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "")


def _v(store, s, nd=2):
    x = latest_value(store, s)
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:,.{nd}f}"


def _delta_txt(store, s, bp=False, pct=False):
    h = history(store, s)
    if len(h) < 2:
        return "", FAINT
    chg = float(h.iloc[-1]["value"]) - float(h.iloc[-2]["value"])
    last = float(h.iloc[-1]["value"])
    col = POS if chg > 0 else (NEG if chg < 0 else FAINT)
    sign = "+" if chg >= 0 else "-"
    if bp:
        return f"{sign}{abs(chg) * 100:,.0f} bp", col
    if pct and (last - chg) != 0:
        return f"{sign}{abs(chg / (last - chg)) * 100:,.2f}%", col
    return f"{sign}{abs(chg):,.2f}", col


def build_email(store) -> tuple[str, str]:
    ex = build_explainers(store)
    tz = ZoneInfo(config.MARKET_TZ)
    today = datetime.now(tz).strftime("%A, %d %B %Y")
    subject = f"Merit Order — {_strip(ex['headline']).rstrip('.')}"

    # key metrics row
    metrics = [
        ("US 10Y", _v(store, "rate.ust_10y") + "%", _delta_txt(store, "rate.ust_10y", bp=True)),
        ("2s10s", _v(store, "derived.curve_2s10s", 0) + " bp", ("", FAINT)),
        ("Broad USD", _v(store, "fx.usd_broad"), _delta_txt(store, "fx.usd_broad", pct=True)),
        ("VIX", _v(store, "vol.vix"), _delta_txt(store, "vol.vix", pct=True)),
        ("Brent", "$" + _v(store, "oil.brent"), _delta_txt(store, "oil.brent", pct=True)),
        ("Henry Hub", "$" + _v(store, "gas.henry_hub"), _delta_txt(store, "gas.henry_hub", pct=True)),
    ]

    def metric_cell(label, val, dt):
        chg, col = dt
        return (
            f'<td style="padding:12px 14px;border:1px solid {LINE};vertical-align:top;">'
            f'<div style="font:600 10px/1 Arial,sans-serif;letter-spacing:1.5px;'
            f'text-transform:uppercase;color:{FAINT};margin-bottom:7px;">{label}</div>'
            f'<div style="font:600 19px/1 Georgia,serif;color:{INK};">{val}</div>'
            f'<div style="font:12px/1 Arial,sans-serif;color:{col};margin-top:5px;">{chg}&nbsp;</div></td>'
        )

    rows = ""
    for i in range(0, len(metrics), 3):
        cells = "".join(metric_cell(*m) for m in metrics[i:i + 3])
        rows += f"<tr>{cells}</tr>"
    metrics_table = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="width:100%;border-collapse:collapse;margin:6px 0 8px;">{rows}</table>'
    )

    # explainer blocks
    blocks = ""
    for s in ex["sections"]:
        blocks += (
            f'<div style="margin:22px 0 0;padding:0 0 0 16px;border-left:3px solid {ACCENT};">'
            f'<div style="font:600 17px/1.3 Georgia,serif;color:{INK};margin-bottom:6px;">{s["title"]}</div>'
            f'<div style="font:14px/1.6 Arial,sans-serif;color:{SUB};margin-bottom:10px;">{s["plain"]}</div>'
            f'<div style="font:600 10px/1 Arial,sans-serif;letter-spacing:1.5px;text-transform:uppercase;'
            f'color:{ACCENT};margin-bottom:4px;">What\'s happening today</div>'
            f'<div style="font:14px/1.6 Arial,sans-serif;color:{INK};margin-bottom:10px;">{s["today"]}</div>'
            f'<div style="font:600 10px/1 Arial,sans-serif;letter-spacing:1.5px;text-transform:uppercase;'
            f'color:{ACCENT};margin-bottom:4px;">Why it matters</div>'
            f'<div style="font:14px/1.6 Arial,sans-serif;color:{SUB};">{s["matters"]}</div></div>'
        )

    cta = ""
    if config.SITE_URL:
        cta = (f'<a href="{config.SITE_URL}" style="display:inline-block;margin:8px 0 2px;'
               f'padding:11px 20px;background:{INK};color:#fff;border-radius:8px;'
               f'font:600 13px Arial,sans-serif;text-decoration:none;">Open the full dashboard &rarr;</a>')

    html = f"""\
<!doctype html><html><body style="margin:0;background:{CANVAS};padding:24px 0;">
<table role="presentation" cellpadding="0" cellspacing="0" align="center"
 style="width:600px;max-width:92%;background:{CARD};border:1px solid {LINE};border-radius:16px;overflow:hidden;">
  <tr><td style="padding:26px 30px 0;">
    <div style="font:600 12px/1 Arial,sans-serif;letter-spacing:3px;text-transform:uppercase;color:{ACCENT};">◆ Merit Order</div>
    <div style="font:13px/1 Arial,sans-serif;color:{FAINT};margin-top:8px;">{today} · Morning briefing</div>
    <h1 style="font:500 26px/1.25 Georgia,serif;color:{INK};margin:16px 0 4px;">{ex['headline']}</h1>
  </td></tr>
  <tr><td style="padding:14px 30px 0;">{metrics_table}</td></tr>
  <tr><td style="padding:6px 30px 4px;">{blocks}</td></tr>
  <tr><td style="padding:22px 30px 8px;">{cta}</td></tr>
  <tr><td style="padding:14px 30px 26px;border-top:1px solid {LINE};">
    <div style="font:11px/1.6 Arial,sans-serif;color:{FAINT};">
      Generated automatically from public data (FRED, Open-Meteo). Items marked as assumptions have no free daily feed.
      Educational project — not investment advice.</div>
  </td></tr>
</table></body></html>"""
    return subject, html


def send_digest(store) -> str:
    if not config.ENABLE_EMAIL:
        return "email: disabled (no EMAIL_USER/EMAIL_PASS)"
    try:
        subject, html = build_email(store)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = config.EMAIL_USER
        msg["To"] = config.EMAIL_TO
        msg.set_content(_strip(html.split("</h1>")[0]).strip() or "Merit Order morning briefing")
        msg.add_alternative(html, subtype="html")

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx) as server:
            server.login(config.EMAIL_USER, config.EMAIL_PASS)
            server.send_message(msg)
        return f"email: sent to {config.EMAIL_TO}"
    except Exception as exc:  # never let email failure break the pipeline
        return f"email: failed ({type(exc).__name__}: {exc})"
