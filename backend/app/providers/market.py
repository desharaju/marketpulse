import asyncio
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx

from app.analytics import NEW_YORK, intraday_relative_volume
from app.config import Settings

UTC = timezone.utc
FIXTURES = [
    {"symbol": "NVDA", "company": "NVIDIA Corporation", "price": 142.65, "change": 3.12, "changePercent": 2.24, "volume": 31_400_000, "averageVolume": 24_800_000, "marketCap": 3_480_000_000_000},
    {"symbol": "TSLA", "company": "Tesla, Inc.", "price": 318.40, "change": -8.25, "changePercent": -2.53, "volume": 22_800_000, "averageVolume": 18_100_000, "marketCap": 1_020_000_000_000},
    {"symbol": "PLTR", "company": "Palantir Technologies Inc.", "price": 74.26, "change": 5.08, "changePercent": 7.34, "volume": 18_300_000, "averageVolume": 7_500_000, "marketCap": 170_000_000_000},
    {"symbol": "AMD", "company": "Advanced Micro Devices, Inc.", "price": 166.82, "change": 1.94, "changePercent": 1.18, "volume": 12_100_000, "averageVolume": 10_300_000, "marketCap": 270_000_000_000},
    {"symbol": "AAPL", "company": "Apple Inc.", "price": 230.11, "change": 0.44, "changePercent": 0.19, "volume": 11_700_000, "averageVolume": 15_200_000, "marketCap": 3_520_000_000_000},
    {"symbol": "COIN", "company": "Coinbase Global, Inc.", "price": 248.90, "change": -4.72, "changePercent": -1.86, "volume": 8_600_000, "averageVolume": 5_400_000, "marketCap": 61_000_000_000},
]


class MarketDataProvider(Protocol):
    name: str
    mode: str

    async def fetch_stocks(self, symbols: list[str]) -> dict: ...

    async def fetch_news(self, symbol: str) -> list[dict]: ...


class DemoProvider:
    name = "Illustrative fixtures"
    mode = "demo"

    async def fetch_stocks(self, symbols: list[str]) -> dict:
        rows = [dict(row) for row in FIXTURES if row["symbol"] in symbols]
        for row in rows:
            row.update({
                "relativeVolume": round(row["volume"] / row["averageVolume"], 2),
                "fullDayRvolEstimate": None,
                "dollarVolume": round(row["price"] * row["volume"], 2),
                "premarket": None,
                "premarketUnavailableReason": "Not included in illustrative fixtures",
                "source": self.name,
                "asOf": None,
                "simulated": True,
                "dataQuality": "illustrative",
            })
        return {
            "mode": self.mode,
            "source": self.name,
            "asOf": None,
            "delayStatus": "not-market-data",
            "simulated": True,
            "limitations": ["Fixed illustrative fixtures; not current or historical market observations."],
            "items": rows,
        }

    async def fetch_news(self, symbol: str) -> list[dict]:
        return []

    async def fetch_history(self, symbol: str, resolution: str = "5") -> list[dict]:
        row = next((item for item in FIXTURES if item["symbol"] == symbol), None)
        if not row:
            return []
        offsets = [-1.4, -0.8, -1.1, -0.2, 0.4, 0.1, 0.9, 0.5, 1.2, 0.8, 1.5, 1.1]
        start = datetime(2025, 1, 6, 9, 30, tzinfo=NEW_YORK)
        return [{
            "time": (start + timedelta(minutes=5 * index)).isoformat(),
            "value": round(row["price"] + offset, 2),
            "volume": 120_000 + index * 23_000,
            "simulated": True,
        } for index, offset in enumerate(offsets)]


class FinnhubProvider:
    name = "Finnhub"
    mode = "provider"
    base_url = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str, timeout_seconds: float = 8.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(3)
        self._cached_at: datetime | None = None
        self._cached_symbols: tuple[str, ...] = ()
        self._cached_result: dict | None = None

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        async with self._semaphore:
            response = await client.get(f"{self.base_url}/{path}", params={**params, "token": self.api_key})
            response.raise_for_status()
            return response.json()

    async def fetch_stocks(self, symbols: list[str]) -> dict:
        now = datetime.now(UTC)
        key = tuple(sorted(symbols))
        if self._cached_result and self._cached_at and now - self._cached_at < timedelta(seconds=30) and key == self._cached_symbols:
            return {**self._cached_result, "cacheStatus": "cached"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async def fetch_symbol(symbol: str) -> dict:
                try:
                    quote, candles = await asyncio.gather(
                        self._get(client, "quote", {"symbol": symbol}),
                        self._get(client, "stock/candle", {
                            "symbol": symbol,
                            "resolution": "5",
                            "from": int((now - timedelta(days=35)).timestamp()),
                            "to": int(now.timestamp()),
                        }),
                    )
                    return self._normalize(symbol, quote, candles, now)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    return {"symbol": symbol, "error": self._safe_error(exc)}

            results = await asyncio.gather(*(fetch_symbol(symbol) for symbol in symbols))

        items = [item for item in results if "error" not in item]
        errors = [{"symbol": item["symbol"], "message": item["error"]} for item in results if "error" in item]
        updated = max((item["asOf"] for item in items if item.get("asOf")), default=None)
        snapshot = {
            "mode": self.mode,
            "source": self.name,
            "asOf": updated,
            "delayStatus": "plan-dependent",
            "simulated": False,
            "limitations": [
                "Quote delay and exchange coverage depend on your Finnhub plan and exchange entitlements.",
                "Premarket trade data is not provided by this scanner adapter.",
                "Only the configured symbol universe is scanned.",
            ],
            "errors": errors,
            "items": items,
        }
        if items:
            self._cached_symbols = key
            self._cached_at = now
            self._cached_result = snapshot
        return snapshot

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"Provider returned HTTP {error.response.status_code}"
        if isinstance(error, httpx.TimeoutException):
            return "Provider request timed out"
        if isinstance(error, httpx.RequestError):
            return "Provider request failed"
        return "Provider response could not be normalized"

    @staticmethod
    def _normalize(symbol: str, quote: dict, candles: dict, now: datetime) -> dict:
        if quote.get("c") is None or quote.get("c", 0) <= 0:
            raise ValueError("Quote unavailable")
        if candles.get("s") not in {"ok", "no_data"}:
            raise ValueError("Intraday candles unavailable")

        bars = []
        for stamp, volume in zip(candles.get("t", []), candles.get("v", [])):
            timestamp = datetime.fromtimestamp(stamp, UTC).astimezone(NEW_YORK)
            if timestamp.time() >= datetime.strptime("09:30", "%H:%M").time() and timestamp.time() < datetime.strptime("16:00", "%H:%M").time():
                bars.append({"timestamp": timestamp, "volume": max(0, float(volume or 0))})

        today = now.astimezone(NEW_YORK).date()
        current_bars = [bar for bar in bars if bar["timestamp"].date() == today and bar["timestamp"] <= now.astimezone(NEW_YORK)]
        historical = {}
        for bar in bars:
            day = bar["timestamp"].date()
            if day < today:
                historical.setdefault(day, []).append(bar)
        sessions = [historical[day] for day in sorted(historical)[-20:]]
        baseline = intraday_relative_volume(current_bars, sessions)
        current_volume = sum(bar["volume"] for bar in current_bars) if current_bars else None
        average_volume = (sum(bar["volume"] for session in sessions for bar in session) / len(sessions)) if sessions else None
        price = float(quote["c"])
        change = float(quote.get("d") or 0)
        quote_time = datetime.fromtimestamp(int(quote["t"]), UTC) if quote.get("t") else None
        return {
            "symbol": symbol,
            "company": symbol,
            "price": price,
            "change": change,
            "changePercent": float(quote.get("dp") or 0),
            "volume": round(current_volume) if current_volume is not None else None,
            "averageVolume": round(average_volume) if average_volume is not None else None,
            "relativeVolume": baseline["relativeVolume"],
            "fullDayRvolEstimate": baseline["fullDayEstimate"],
            "baselineSessions": baseline["baselineSessions"],
            "dollarVolume": round(price * current_volume, 2) if current_volume is not None else None,
            "marketCap": None,
            "premarket": None,
            "premarketUnavailableReason": "Finnhub scanner adapter does not include premarket trades",
            "source": "Finnhub",
            "asOf": quote_time.isoformat() if quote_time else now.isoformat(),
            "simulated": False,
            "dataQuality": "provider; subscription-dependent delay",
        }

    async def fetch_news(self, symbol: str) -> list[dict]:
        today = datetime.now(UTC).date()
        params = {"symbol": symbol, "from": (today - timedelta(days=7)).isoformat(), "to": today.isoformat()}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            rows = await self._get(client, "company-news", params)
        normalized = []
        seen = set()
        for row in rows:
            url = row.get("url")
            headline = row.get("headline")
            if not url or not headline or url in seen:
                continue
            seen.add(url)
            normalized.append({
                "symbol": symbol,
                "headline": headline,
                "publisher": row.get("source") or "Finnhub",
                "publishedAt": datetime.fromtimestamp(row["datetime"], UTC).isoformat() if row.get("datetime") else None,
                "url": url,
                "summary": row.get("summary"),
                "source": "Finnhub",
                "ingestedAt": datetime.now(UTC).isoformat(),
            })
        return normalized

    async def fetch_history(self, symbol: str, resolution: str = "5") -> list[dict]:
        now = datetime.now(UTC)
        days = 5 if resolution == "D" else 2
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = await self._get(client, "stock/candle", {
                "symbol": symbol,
                "resolution": resolution,
                "from": int((now - timedelta(days=days)).timestamp()),
                "to": int(now.timestamp()),
            })
        if payload.get("s") != "ok":
            return []
        return [{
            "time": datetime.fromtimestamp(stamp, UTC).isoformat(),
            "value": close,
            "volume": volume,
            "simulated": False,
        } for stamp, close, volume in zip(payload.get("t", []), payload.get("c", []), payload.get("v", []))]


def create_provider(settings: Settings) -> MarketDataProvider:
    if settings.finnhub_api_key:
        return FinnhubProvider(settings.finnhub_api_key)
    return DemoProvider()