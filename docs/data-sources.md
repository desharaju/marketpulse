# Data Sources and Limitations

## Finnhub (optional)

Official API reference: https://finnhub.io/docs/api

MarketPulse uses `GET /api/v1/quote`, `GET /api/v1/stock/candle`, and `GET /api/v1/company-news`. Configure `FINNHUB_API_KEY` server-side. Request access, exchange entitlements, rate limits, real-time/delayed status, premarket coverage, retention, redistribution, and commercial-display rights vary by plan and may change. Verify the current Finnhub terms and account dashboard before enabling public or commercial use. MarketPulse labels the provider and timestamps returned observations, and does not claim real-time service based only on the presence of a key. The current adapter does not claim premarket trades; that section remains unavailable for Finnhub.

The initial scanner queries only `MARKET_SYMBOLS`, not every listed US security. API rate limits and available history can leave volume fields unavailable. Comparable-period RVOL requires completed prior sessions with bars at the corresponding interval. No historical licensed bars are persisted.

## SEC EDGAR (not yet enabled)

Official API documentation: https://www.sec.gov/edgar/sec-api-documentation

EDGAR submissions and XBRL endpoints are potential public company-disclosure sources. Before enabling, configure an identifying `User-Agent`, observe SEC fair-access limits, link to source filings, and distinguish filing acceptance time from ingestion time. This release does not claim to fetch or classify filings.

## Demo mode

When no provider key is configured, the dashboard shows fixed illustrative fixtures marked `DEMO`, `simulated`, and not live. They are not generated from current market conditions and must not be used for trading decisions. If a configured provider fails, the API returns an unavailable status and does not substitute demo values.