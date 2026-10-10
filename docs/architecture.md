# Architecture and Implementation Plan

## Current architecture

- `frontend/`: Next.js App Router interface. It calls the API and displays provider mode, source, and freshness rather than generating market values in the browser.
- `backend/app/providers/`: provider protocol and adapters. Scanner and ranking code consume normalized values only.
- `backend/app/analytics.py`: time-zone-aware market calendar helpers, comparable-period relative volume, and explainable scoring.
- `backend/app/`: FastAPI API, persistence, report generation, SMTP delivery, and the single-process APScheduler.
- PostgreSQL is the Compose database. API-only development may use SQLite; tables are initialized by the application. Schema changes are managed by Alembic.

## Data contracts and trust

Every market response identifies `mode` (`demo` or `provider`), `source`, `asOf`, `delayStatus`, and `limitations`. Demo fixtures are fixed illustrative examples and are marked `simulated: true`. Provider errors are returned as unavailable/stale status; they never trigger fabricated quotes. Missing premarket or index fields remain unavailable. Provider credentials stay server-side.

Finnhub is the first optional integration because its documented REST API provides quotes, intraday candles, and company news. Live/delayed status, premarket availability, and request limits are subscription- and exchange-dependent. The configured symbol universe is deliberately bounded. Intraday relative volume compares cumulative volume through the current five-minute interval with the same interval accumulated on prior sessions; full-session RVOL is estimated from prior-session cumulative-volume fractions. Insufficient history is reported as unavailable rather than guessed.

## Delivery plan

1. Foundation: documented service boundaries, environment configuration, provider protocol, calendar/scoring utilities, and deterministic tests.
2. Working product: database-backed API, scanner views, responsive dashboard, Docker health checks, and truthful demo mode.
3. Provider data: Finnhub quotes/candles/news, bounded polling/cache, freshness and limitations surfaced in the UI.
4. Reports: preview and generation, idempotent report records, SMTP test-send, and trading-day scheduler.
5. Operations: migrations, CI, tests, PowerShell setup, source/licensing notes, and deployment guidance.

## Runtime and reliability choices

The API uses a bounded async HTTP client, finite timeouts, a small TTL cache, and low concurrency. The scheduler runs only in the API service and checks the XNYS calendar in `America/New_York`; report rows are unique by recipient and market date. SMTP is disabled until configured. For high availability, move scheduling to a dedicated worker and use a distributed job queue/lock before scaling scheduler processes.

## Future boundaries

Authentication, multi-user isolation, distributed scheduling, broker connections, AI summaries, and licensed whole-market streaming are intentionally outside the initial single-user deployment. The adapter interfaces and report/watchlist tables keep those additions isolated. News is linked to its publisher and never treated as proof of price-move causality.