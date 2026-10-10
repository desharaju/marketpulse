from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import generate_for_recipient
from app.models import ReportConfig
from app.reports import build_report, render_report
import app.main as main


def test_report_filters_candidates_before_top_n_and_marks_premarket_unavailable():
    snapshot = {
        "mode": "provider",
        "source": "test provider",
        "items": [
            {"symbol": "LOW", "price": 2, "volume": 10000, "dollarVolume": 20000, "relativeVolume": 5, "changePercent": 4},
            {"symbol": "NO-RVOL", "price": 15, "volume": 5000, "dollarVolume": 75000, "relativeVolume": None, "changePercent": 4},
            {"symbol": "QUALIFIED", "price": 12, "volume": 1000, "dollarVolume": 12000, "relativeVolume": 3, "changePercent": 2},
            {"symbol": "LOW-RVOL", "price": 15, "volume": 800, "dollarVolume": 12000, "relativeVolume": 1.2, "changePercent": 4},
        ],
    }
    config = ReportConfig(min_price=5, min_dollar_volume=10000, min_relative_volume=2, min_change_percent=1, max_tickers_per_section=1)

    report = build_report(snapshot, "https://dashboard.example", date(2025, 1, 6), config)

    assert report["sections"][0]["status"] == "unavailable"
    assert report["sections"][0]["items"] == []
    assert [row["symbol"] for row in report["sections"][3]["items"]] == ["QUALIFIED"]


def test_html_report_escapes_market_text_and_includes_plain_text():
    report = build_report({"mode": "demo", "items": [{
        "symbol": "SAFE", "company": "<img src=x onerror=alert(1)>", "price": 1, "changePercent": 1,
        "volume": 1, "relativeVolume": 1, "dollarVolume": 1,
    }]}, "https://dashboard.example")
    html, text = render_report(report)

    assert "<img src=x" not in html
    assert "&lt;img" in html
    assert "MarketPulse Premarket Intelligence" in text
    assert "DEMO ONLY" in " ".join(report["limitations"])


@pytest.mark.asyncio
async def test_report_send_is_idempotent_for_recipient_and_date(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'reports.db'}")
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", test_sessions)
    sent = []

    async def fixture_snapshot(force=False):
        return {"mode": "demo", "source": "test fixtures", "asOf": None, "items": [], "limitations": []}

    monkeypatch.setattr(main.scanner, "snapshot", fixture_snapshot)
    monkeypatch.setattr(main, "run_email", lambda recipient, subject, report: sent.append(recipient))

    first = await generate_for_recipient("research@example.test")
    second = await generate_for_recipient("research@example.test")

    assert first["status"] == "sent"
    assert second["duplicate"] is True
    assert sent == ["research@example.test"]
    engine.dispose()