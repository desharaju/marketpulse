import json
import smtplib
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from html import escape

from app.config import Settings
from app.models import ReportConfig

NEW_YORK = ZoneInfo("America/New_York")


def build_report(snapshot: dict, dashboard_url: str, report_date: date | None = None, config: ReportConfig | None = None) -> dict:
    items = snapshot.get("items", [])
    if config:
        items = [row for row in items if
            (row.get("price") or 0) >= config.min_price and
            (row.get("dollarVolume") or 0) >= config.min_dollar_volume and
            (row.get("relativeVolume") is not None and row["relativeVolume"] >= config.min_relative_volume) and
            (row.get("changePercent") is None or abs(row["changePercent"]) >= config.min_change_percent)]
    section_limit = config.max_tickers_per_section if config else 10
    active = sorted(items, key=lambda row: row.get("volume") or -1, reverse=True)[:section_limit]
    unusual = sorted((row for row in items if row.get("relativeVolume") is not None), key=lambda row: row["relativeVolume"], reverse=True)[:section_limit]
    generated = datetime.now(timezone.utc).isoformat()
    premarket_sections = [
        {"title": "Premarket gainers", "items": [], "status": "unavailable"},
        {"title": "Premarket losers", "items": [], "status": "unavailable"},
        {"title": "Unusual premarket volume", "items": [], "status": "unavailable"},
    ]
    sections = premarket_sections + [
        {"title": "Most active in available scanner session", "items": active, "status": "available" if active else "unavailable"},
        {"title": "Unusual volume in available scanner session", "items": unusual, "status": "available" if unusual else "unavailable"},
        {"title": "Trending tickers with verified catalysts", "items": [], "status": "unavailable"},
        {"title": "Earnings and company events", "items": [], "status": "unavailable"},
        {"title": "SEC filings and corporate announcements", "items": [], "status": "unavailable"},
        {"title": "Watchlist activity", "items": [], "status": "unavailable"},
    ]
    sections[3]["items"] = active
    sections[4]["items"] = unusual
    if snapshot.get("mode") == "demo":
        limitations = ["DEMO ONLY: fixtures are illustrative and are not live market data."] + snapshot.get("limitations", [])
    else:
        limitations = list(snapshot.get("limitations", []))
    limitations.extend([
        "Premarket trades are unavailable from the configured scanner provider; premarket sections contain no substitute regular-session observations.",
        "Index futures, earnings calendar, SEC filings, and catalyst classifications are not enabled in this release.",
    ])
    return {
        "reportDate": (report_date or datetime.now(NEW_YORK).date()).isoformat(),
        "generatedAt": generated,
        "dataAsOf": snapshot.get("asOf"),
        "source": snapshot.get("source"),
        "mode": snapshot.get("mode"),
        "delayStatus": snapshot.get("delayStatus"),
        "marketSession": snapshot.get("marketSession"),
        "sections": sections,
        "limitations": limitations,
        "dashboardUrl": dashboard_url,
    }


def render_report(report: dict) -> tuple[str, str]:
    lines = [f"MarketPulse Premarket Intelligence | {report['reportDate']}", ""]
    html_sections = []
    for section in report["sections"]:
        lines.extend([section["title"], "-" * len(section["title"])])
        rows = []
        if not section["items"]:
            lines.append("No data available.")
            rows.append("<p>No data available.</p>")
        for row in section["items"]:
            change = row.get("changePercent")
            summary = f"{row['symbol']} {row.get('company') or ''} | price {row.get('price', 'unavailable')} | change {f'{change:+.2f}%' if change is not None else 'unavailable'} | volume {row.get('volume', 'unavailable')} | RVOL {row.get('relativeVolume', 'unavailable')}"
            lines.append(summary)
            rows.append(f"<li><strong>{escape(row['symbol'])}</strong> {escape(row.get('company') or '')} · price {escape(str(row.get('price', 'unavailable')))} · change {escape(f'{change:+.2f}%' if change is not None else 'unavailable')} · volume {escape(str(row.get('volume', 'unavailable')))} · RVOL {escape(str(row.get('relativeVolume', 'unavailable')))}</li>")
        html_sections.append(f"<h2>{escape(section['title'])}</h2><ul>{''.join(rows)}</ul>")
        lines.append("")

    lines.extend(["Data limitations", *[f"- {item}" for item in report["limitations"]], "", f"Source: {report.get('source') or 'unavailable'} | data as of: {report.get('dataAsOf') or 'not available'}", report["dashboardUrl"]])
    html = (
        "<!doctype html><html><body style='font-family:Arial,sans-serif;color:#18231f'>"
        f"<h1>MarketPulse Premarket Intelligence</h1><p>{escape(report['reportDate'])} · {escape(str(report.get('mode', 'unavailable')).upper())} · data as of {escape(str(report.get('dataAsOf') or 'not available'))}</p>"
        + "".join(html_sections)
        + f"<h2>Data limitations</h2><ul>{''.join(f'<li>{escape(item)}</li>' for item in report['limitations'])}</ul>"
        + f"<p>Source: {escape(str(report.get('source') or 'unavailable'))} · <a href='{escape(report['dashboardUrl'], quote=True)}'>Open MarketPulse</a></p></body></html>"
    )
    return html, "\n".join(lines)


def deliver_email(settings: Settings, recipient: str, subject: str, html: str, text: str, retries: int = 3) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP is not configured; set SMTP_HOST and SMTP_FROM")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    for attempt in range(retries):
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
            return
        except (smtplib.SMTPException, OSError):
            if attempt + 1 == retries:
                raise
            time.sleep(2 ** attempt)


def filtered_sections(report: dict, config: ReportConfig) -> dict:
    max_items = config.max_tickers_per_section
    minimum = config.min_dollar_volume
    min_price = config.min_price
    for section in report["sections"]:
        rows = section["items"]
        section["items"] = [row for row in rows if
            (row.get("price") or 0) >= min_price and
            (row.get("dollarVolume") or 0) >= minimum and
            (row.get("relativeVolume") is not None and row["relativeVolume"] >= config.min_relative_volume) and
            (row.get("changePercent") is None or abs(row["changePercent"]) >= config.min_change_percent)][:max_items]
    return report


def serialize_report_payload(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))