"""Email subject/body rendering for alerts."""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from html import escape

from ..models import Alert, AlertKind

FOOTER = "This is an automated alert from Scan My Sites."


def render(alert: Alert, tz: tzinfo) -> tuple[str, str, str]:
    """Returns (subject, html_body, text_body)."""
    result = alert.result
    ep = result.endpoint
    rows: list[tuple[str, str]] = [("Endpoint", ep.name), ("URL", ep.url), ("Type", ep.type)]

    if alert.kind is AlertKind.DOWN:
        subject = f"[DOWN] {ep.name} is not responding"
        heading = f"{ep.name} is DOWN"
        color = "#c62828"
        rows += [
            ("Down since", _fmt(alert.down_since, tz)),
            ("Checked at", _fmt(result.checked_at, tz)),
            ("HTTP status", str(result.http_status or "N/A")),
            ("Error", result.error or "N/A"),
            ("Failed checks", str(alert.consecutive_failures)),
        ]
    else:
        subject = f"[UP] {ep.name} has recovered"
        heading = f"{ep.name} is back UP"
        color = "#2e7d32"
        downtime = result.checked_at - alert.down_since if alert.down_since else None
        rows += [
            ("Down since", _fmt(alert.down_since, tz)),
            ("Recovered at", _fmt(result.checked_at, tz)),
            ("Downtime", _duration(downtime)),
            ("HTTP status", str(result.http_status or "N/A")),
            ("Response time", f"{result.response_time:.2f}s" if result.response_time else "N/A"),
        ]

    table = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#555"><strong>{escape(k)}</strong></td>'
        f'<td style="padding:4px 0">{escape(v)}</td></tr>'
        for k, v in rows
    )
    html = (
        '<div style="font-family:Arial,sans-serif;font-size:14px">'
        f'<h2 style="color:{color};margin:0 0 12px">{escape(heading)}</h2>'
        f"<table>{table}</table>"
        f'<hr><p style="color:#888;font-size:12px">{FOOTER}</p></div>'
    )
    text = "\n".join([heading, "", *(f"{k}: {v}" for k, v in rows), "", FOOTER])
    return subject, html, text


def _fmt(value: datetime | None, tz: tzinfo) -> str:
    return value.astimezone(tz).strftime("%Y-%m-%d %I:%M %p %Z") if value else "N/A"


def _duration(delta: timedelta | None) -> str:
    if delta is None:
        return "N/A"
    minutes, seconds = divmod(int(delta.total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = [f"{n}{unit}" for n, unit in ((days, "d"), (hours, "h"), (minutes, "m")) if n]
    return " ".join(parts) or f"{seconds}s"
