import asyncio
import hmac
import json
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from time import monotonic
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics import market_session, trading_day
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import AlertEvent, AlertRule, EmailDeliveryLog, Report, ReportConfig, Watchlist, WatchlistItem
from app.providers.market import create_provider
from app.reports import build_report, deliver_email, filtered_sections, render_report, serialize_report_payload
from app.scanner import Scanner, freshness
from app.schemas import AlertCreate, ReportConfigUpdate, ReportRequest, TestEmailRequest, WatchlistCreate, WatchlistItemCreate

settings = get_settings()
NEW_YORK = ZoneInfo("America/New_York")
provider = create_provider(settings)
scanner = Scanner(provider, settings)
scheduler = AsyncIOScheduler(timezone="America/New_York")
ADMIN_REQUESTS: dict[str, list[float]] = {}


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def run_email(recipient: str, subject: str, report: dict) -> None:
    html, plain = render_report(report)
    deliver_email(settings, recipient, subject, html, plain)


async def generate_for_recipient(recipient: str, send: bool = True) -> dict:
    snapshot = await scanner.snapshot(force=True)
    today = datetime.now(NEW_YORK).date()
    session = SessionLocal()
    try:
        config = session.get(ReportConfig, 1)
        report = build_report(snapshot, settings.dashboard_url, today, config)
        if config:
            report = filtered_sections(report, config)
        existing = session.scalar(select(Report).where(Report.recipient == recipient, Report.report_date == today))
        if existing:
            if not send or existing.status == "sent":
                return {"id": existing.id, "status": existing.status, "report": json.loads(existing.payload_json), "duplicate": True}
            report = json.loads(existing.payload_json)
            record = existing
        else:
            record = Report(recipient=recipient, report_date=today, status="generated", payload_json=serialize_report_payload(report))
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise ValueError("A report already exists for this recipient and trading date")
            session.refresh(record)
        if send:
            claim = session.execute(update(Report).where(Report.id == record.id, Report.status.in_(["generated", "failed"])).values(status="sending"))
            session.commit()
            if claim.rowcount != 1:
                return {"id": record.id, "status": record.status, "report": report, "duplicate": True}
            try:
                await asyncio.to_thread(run_email, recipient, f"MarketPulse Premarket Intelligence | {today.isoformat()}", report)
                record.status = "sent"
                record.sent_at = datetime.now(timezone.utc)
                session.add(EmailDeliveryLog(report_id=record.id, recipient=recipient, status="sent"))
            except Exception as exc:
                record.status = "failed"
                record.error = str(exc)[:1000]
                session.add(EmailDeliveryLog(report_id=record.id, recipient=recipient, status="failed", error=record.error))
            session.commit()
        return {"id": record.id, "status": record.status, "report": report, "duplicate": False, "error": record.error}
    finally:
        session.close()


async def scheduled_report() -> None:
    current = datetime.now(NEW_YORK)
    today = current.date()
    if not trading_day(today):
        return
    session = SessionLocal()
    try:
        config = session.get(ReportConfig, 1)
        recipients = (config.recipient if config else settings.report_recipient).split(",")
        report_time = config.report_time if config else settings.report_time
    finally:
        session.close()
    if current.strftime("%H:%M") != report_time:
        return
    for recipient in filter(None, (value.strip() for value in recipients)):
        try:
            await generate_for_recipient(recipient)
        except Exception:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env == "production" and not settings.admin_api_key:
        raise RuntimeError("ADMIN_API_KEY is required in production")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if not session.get(ReportConfig, 1):
            session.add(ReportConfig(id=1, recipient=settings.report_recipient, report_time=settings.report_time))
            session.commit()
    scheduler.add_job(scheduled_report, CronTrigger(second=0), id="premarket-report", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="MarketPulse API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=False, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type", "X-Admin-Key"])


def require_admin(request: Request, admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    now = monotonic()
    client = request.client.host if request.client else "unknown"
    recent = [timestamp for timestamp in ADMIN_REQUESTS.get(client, []) if now - timestamp < 60]
    if len(recent) >= 30:
        raise HTTPException(status_code=429, detail="Too many administrative requests; retry shortly")
    recent.append(now)
    ADMIN_REQUESTS[client] = recent
    if settings.admin_api_key and not hmac.compare_digest(admin_key or "", settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Valid X-Admin-Key header required")


def observe_alerts(session: Session, items: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    rules = session.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))).all()
    by_symbol = {item["symbol"]: item for item in items}
    for rule in rules:
        item = by_symbol.get(rule.symbol)
        if not item:
            continue
        value = item.get({"relativeVolume": "relativeVolume", "changePercent": "changePercent", "price": "price"}[rule.metric])
        last_triggered = rule.last_triggered_at
        if last_triggered and last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=timezone.utc)
        if value is None or (last_triggered and (now - last_triggered).total_seconds() < 1800):
            continue
        triggered = value >= rule.threshold if rule.direction == "above" else value <= rule.threshold
        if triggered:
            session.add(AlertEvent(rule_id=rule.id, symbol=rule.symbol, message=f"{rule.symbol} {rule.metric} {rule.direction} {rule.threshold:g} (observed {value:g})"))
            rule.last_triggered_at = now
    session.commit()


@app.get("/api/health")
def health(session: Session = Depends(get_db)):
    try:
        session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "unavailable"
    return {"status": "ok" if database_status == "ok" else "degraded", "database": database_status, "provider": provider.name, "providerMode": provider.mode, "providerConfigured": provider.mode == "provider", "schedulerRunning": scheduler.running}


@app.get("/api/market/overview")
async def market_overview(refresh: bool = False):
    snapshot = await scanner.snapshot(force=refresh)
    return {
        **{key: snapshot.get(key) for key in ("mode", "source", "asOf", "delayStatus", "simulated", "limitations", "errors", "cacheStatus", "marketSession")},
        "freshness": freshness(snapshot),
        "indices": [],
        "indicesStatus": "unavailable",
        "breadth": None,
        "breadthStatus": "unavailable",
        "symbolCount": len(snapshot.get("items", [])),
    }


@app.get("/api/stocks/most-active")
async def most_active(
    sort_by: str = Query("volume", pattern="^(volume|dollarVolume|changePercent|change)$"),
    min_price: float | None = Query(None, ge=0), max_price: float | None = Query(None, ge=0),
    min_volume: int | None = Query(None, ge=0), search: str | None = None,
    refresh: bool = False,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    session: Session = Depends(get_db),
):
    snapshot = await scanner.snapshot(force=refresh)
    observe_alerts(session, snapshot.get("items", []))
    items = _filter_stocks(snapshot.get("items", []), min_price, max_price, min_volume, search)
    items.sort(key=lambda item: item.get(sort_by) if item.get(sort_by) is not None else float("-inf"), reverse=True)
    return {**_metadata(snapshot), "items": items[(page - 1) * page_size:page * page_size], "total": len(items), "page": page, "pageSize": page_size}


@app.get("/api/stocks/trending")
async def trending(limit: int = Query(25, ge=1, le=100), refresh: bool = False, session: Session = Depends(get_db)):
    snapshot = await scanner.snapshot(force=refresh)
    observe_alerts(session, snapshot.get("items", []))
    items = sorted(snapshot.get("items", []), key=lambda item: item["ranking"]["score"], reverse=True)[:limit]
    return {**_metadata(snapshot), "items": items, "rankingFormula": "bounded relative volume (40%), absolute change magnitude (30%), dollar volume (20%), catalyst (10%); absent signals are excluded and remaining weights renormalized"}


@app.get("/api/stocks/unusual-volume")
async def unusual_volume(threshold: float = Query(2, ge=1, le=100), limit: int = Query(25, ge=1, le=100), refresh: bool = False, session: Session = Depends(get_db)):
    snapshot = await scanner.snapshot(force=refresh)
    observe_alerts(session, snapshot.get("items", []))
    items = [item for item in snapshot.get("items", []) if item.get("relativeVolume") is not None and item["relativeVolume"] >= threshold]
    items.sort(key=lambda item: item["relativeVolume"], reverse=True)
    return {**_metadata(snapshot), "items": items[:limit], "threshold": threshold, "baseline": "same five-minute clock intervals over up to 20 prior sessions; current session excluded"}


@app.get("/api/stocks/premarket")
async def premarket(view: str = Query("all", pattern="^(all|gainers|losers|unusual)$"), refresh: bool = False):
    snapshot = await scanner.snapshot(force=refresh)
    return {**_metadata(snapshot), "items": [], "view": view, "status": "unavailable", "limitation": "Premarket trades are not supplied by the configured provider adapter; regular-session values are not substituted."}


@app.get("/api/news")
async def market_news(limit: int = Query(30, ge=1, le=100)):
    if provider.mode == "demo":
        return {"source": provider.name, "mode": "demo", "items": [], "errors": [], "status": "unavailable", "limitation": "No illustrative news stories are generated."}
    results = await asyncio.gather(*(provider.fetch_news(symbol) for symbol in settings.symbols), return_exceptions=True)
    stories = {}
    errors = []
    for symbol, result in zip(settings.symbols, results):
        if isinstance(result, Exception):
            errors.append({"symbol": symbol, "message": "News provider unavailable"})
            continue
        for story in result:
            key = story.get("url") or re.sub(r"\W+", " ", story.get("headline", "").lower()).strip()
            if key:
                stories.setdefault(key, story)
    items = sorted(stories.values(), key=lambda story: story.get("publishedAt") or "", reverse=True)[:limit]
    return {"source": provider.name, "mode": "provider", "items": items, "errors": errors, "status": "available" if items else "unavailable"}


@app.get("/api/stocks/{ticker}")
async def stock_detail(ticker: str):
    item = await scanner.stock(ticker)
    if not item:
        raise HTTPException(status_code=404, detail="Ticker is not in the configured scanner universe")
    return {"stock": item, "verifiedFacts": ["Provider quote and candle data, when configured"], "calculatedIndicators": ["Comparable-period relative volume", "Dollar volume"], "newsDerivedSummaries": []}


@app.get("/api/stocks/{ticker}/news")
async def stock_news(ticker: str):
    if ticker.upper() not in settings.symbols:
        raise HTTPException(status_code=404, detail="Ticker is not in the configured scanner universe")
    try:
        stories = await provider.fetch_news(ticker.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail="News provider unavailable") from exc
    return {"symbol": ticker.upper(), "source": provider.name, "items": stories, "status": "available" if stories else "unavailable"}


@app.get("/api/stocks/{ticker}/history")
async def stock_history(ticker: str, resolution: str = Query("5", pattern="^(1|5|15|30|60|D)$")):
    if ticker.upper() not in settings.symbols:
        raise HTTPException(status_code=404, detail="Ticker is not in the configured scanner universe")
    if not hasattr(provider, "fetch_history"):
        return {"symbol": ticker.upper(), "source": provider.name, "items": [], "status": "unavailable", "simulated": provider.mode == "demo"}
    try:
        bars = await provider.fetch_history(ticker.upper(), resolution)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="History provider unavailable") from exc
    return {"symbol": ticker.upper(), "source": provider.name, "items": bars, "status": "available" if bars else "unavailable", "simulated": provider.mode == "demo"}


@app.get("/api/watchlists", dependencies=[Depends(require_admin)])
def list_watchlists(session: Session = Depends(get_db)):
    lists = session.scalars(select(Watchlist).order_by(Watchlist.name)).all()
    return [{"id": row.id, "name": row.name, "symbols": [item.symbol for item in row.items]} for row in lists]


@app.post("/api/watchlists", status_code=201, dependencies=[Depends(require_admin)])
def create_watchlist(payload: WatchlistCreate, session: Session = Depends(get_db)):
    row = Watchlist(name=payload.name.strip())
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="A watchlist with this name already exists") from exc
    session.refresh(row)
    return {"id": row.id, "name": row.name, "symbols": []}


@app.post("/api/watchlists/{watchlist_id}/items", status_code=201, dependencies=[Depends(require_admin)])
def add_watchlist_item(watchlist_id: int, payload: WatchlistItemCreate, session: Session = Depends(get_db)):
    row = session.get(Watchlist, watchlist_id)
    if not row:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    session.add(WatchlistItem(watchlist_id=watchlist_id, symbol=payload.symbol))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Ticker already exists in this watchlist") from exc
    return {"watchlistId": watchlist_id, "symbol": payload.symbol}


@app.delete("/api/watchlists/{watchlist_id}/items/{symbol}", status_code=204, dependencies=[Depends(require_admin)])
def remove_watchlist_item(watchlist_id: int, symbol: str, session: Session = Depends(get_db)):
    item = session.scalar(select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.symbol == symbol.upper()))
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist ticker not found")
    session.delete(item)
    session.commit()


@app.get("/api/alerts", dependencies=[Depends(require_admin)])
def list_alerts(session: Session = Depends(get_db)):
    rules = session.scalars(select(AlertRule).order_by(AlertRule.created_at.desc())).all()
    events = session.scalars(select(AlertEvent).order_by(AlertEvent.triggered_at.desc()).limit(100)).all()
    return {"rules": [{"id": r.id, "symbol": r.symbol, "metric": r.metric, "threshold": r.threshold, "direction": r.direction, "enabled": r.enabled} for r in rules], "events": [{"id": e.id, "symbol": e.symbol, "message": e.message, "triggeredAt": e.triggered_at.isoformat()} for e in events]}


@app.post("/api/alerts", status_code=201, dependencies=[Depends(require_admin)])
def create_alert(payload: AlertCreate, session: Session = Depends(get_db)):
    rule = AlertRule(symbol=payload.symbol, metric=payload.metric, threshold=payload.threshold, direction=payload.direction)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return {"id": rule.id, "symbol": rule.symbol, "metric": rule.metric, "threshold": rule.threshold, "direction": rule.direction, "enabled": rule.enabled}


@app.get("/api/reports", dependencies=[Depends(require_admin)])
def list_reports(session: Session = Depends(get_db)):
    rows = session.scalars(select(Report).order_by(Report.created_at.desc()).limit(100)).all()
    return [{"id": row.id, "recipient": row.recipient, "reportDate": row.report_date.isoformat(), "status": row.status, "createdAt": row.created_at.isoformat(), "sentAt": row.sent_at.isoformat() if row.sent_at else None, "error": row.error, "deliveries": [{"status": item.status, "attemptedAt": item.attempted_at.isoformat(), "error": item.error} for item in session.scalars(select(EmailDeliveryLog).where(EmailDeliveryLog.report_id == row.id)).all()]} for row in rows]


@app.get("/api/settings/reports", dependencies=[Depends(require_admin)])
def get_report_settings(session: Session = Depends(get_db)):
    config = session.get(ReportConfig, 1)
    if not config:
        config = ReportConfig(id=1, recipient=settings.report_recipient, report_time=settings.report_time)
    recipients = [address.strip() for address in config.recipient.split(",") if address.strip()]
    return {"recipient": recipients[0] if recipients else "", "additional_recipients": recipients[1:], "report_time": config.report_time, "min_relative_volume": config.min_relative_volume, "min_change_percent": config.min_change_percent, "min_price": config.min_price, "min_dollar_volume": config.min_dollar_volume, "max_tickers_per_section": config.max_tickers_per_section, "format": config.format, "timezone": "America/New_York"}


@app.post("/api/settings/reports", dependencies=[Depends(require_admin)])
def update_report_settings(payload: ReportConfigUpdate, session: Session = Depends(get_db)):
    config = session.get(ReportConfig, 1)
    if not config:
        config = ReportConfig(id=1)
        session.add(config)
    recipients = [str(address) for address in ([payload.recipient] if payload.recipient else []) + payload.additional_recipients]
    config.recipient = ",".join(dict.fromkeys(recipients))
    config.report_time = payload.report_time
    config.min_relative_volume = payload.min_relative_volume
    config.min_change_percent = payload.min_change_percent
    config.min_price = payload.min_price
    config.min_dollar_volume = payload.min_dollar_volume
    config.max_tickers_per_section = payload.max_tickers_per_section
    config.format = payload.format
    session.commit()
    return get_report_settings(session)


@app.post("/api/reports/preview")
async def preview_report(payload: ReportRequest):
    snapshot = await scanner.snapshot(force=True)
    with SessionLocal() as session:
        config = session.get(ReportConfig, 1)
        report = build_report(snapshot, settings.dashboard_url, config=config)
        if config:
            report = filtered_sections(report, config)
    html, plain = render_report(report)
    return {"report": report, "html": html, "text": plain}


@app.post("/api/reports/generate", dependencies=[Depends(require_admin)])
async def generate_report(payload: ReportRequest):
    with SessionLocal() as session:
        config = session.get(ReportConfig, 1)
        configured = (config.recipient if config else settings.report_recipient).split(",")
    recipients = [str(payload.recipient)] if payload.recipient else [address.strip() for address in configured if address.strip()]
    if not recipients:
        raise HTTPException(status_code=422, detail="Configure REPORT_RECIPIENT or provide a recipient")
    try:
        results = [await generate_for_recipient(recipient, payload.send) for recipient in recipients]
        return results[0] if len(results) == 1 else {"results": results}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/reports/send-test", dependencies=[Depends(require_admin)])
async def send_test_email(payload: TestEmailRequest):
    report = build_report(await scanner.snapshot(force=True), settings.dashboard_url)
    html, plain = render_report(report)
    try:
        await asyncio.to_thread(deliver_email, settings, str(payload.recipient), "MarketPulse test email", html, plain)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "sent", "recipient": str(payload.recipient)}


def _metadata(snapshot: dict) -> dict:
    return {key: snapshot.get(key) for key in ("mode", "source", "asOf", "delayStatus", "simulated", "limitations", "errors", "cacheStatus", "marketSession")}


def _filter_stocks(items: list[dict], min_price: float | None, max_price: float | None, min_volume: int | None, search: str | None) -> list[dict]:
    query = search.strip().lower() if search else None
    return [item for item in items if
        (min_price is None or (item.get("price") is not None and item["price"] >= min_price)) and
        (max_price is None or (item.get("price") is not None and item["price"] <= max_price)) and
        (min_volume is None or (item.get("volume") is not None and item["volume"] >= min_volume)) and
        (query is None or query in item["symbol"].lower() or query in (item.get("company") or "").lower())]