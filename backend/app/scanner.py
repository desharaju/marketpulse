from datetime import datetime, timezone
from time import monotonic

from app.analytics import market_session, ranking_score
from app.config import Settings
from app.providers.market import MarketDataProvider


class Scanner:
    def __init__(self, provider: MarketDataProvider, settings: Settings):
        self.provider = provider
        self.settings = settings
        self._snapshot: dict | None = None
        self._snapshot_at = 0.0

    async def snapshot(self, force: bool = False) -> dict:
        if not force and self._snapshot and monotonic() - self._snapshot_at < min(self.settings.refresh_seconds, 60):
            return {**self._snapshot, "marketSession": market_session(), "cacheStatus": "cached"}
        try:
            symbols = await self.provider.fetch_symbols(limit=30)
            snapshot = await self.provider.fetch_stocks(symbols)
        except Exception:
            snapshot = {
                "mode": self.provider.mode,
                "source": self.provider.name,
                "asOf": None,
                "delayStatus": "unavailable",
                "simulated": self.provider.mode == "demo",
                "limitations": ["The configured market-data provider could not be reached."],
                "errors": [{"message": "Market data provider unavailable"}],
                "items": [],
            }
        for item in snapshot.get("items", []):
            signals = {
                "relativeVolume": item.get("relativeVolume"),
                "changePercent": item.get("changePercent"),
                "dollarVolume": item.get("dollarVolume"),
                "catalyst": None,
            }
            item["ranking"] = ranking_score(signals)
        self._snapshot = snapshot
        self._snapshot_at = monotonic()
        return {**snapshot, "marketSession": market_session(), "cacheStatus": "fresh"}

    async def stock(self, symbol: str) -> dict | None:
        snapshot = await self.snapshot()
        return next((item for item in snapshot.get("items", []) if item["symbol"] == symbol.upper()), None)


def freshness(snapshot: dict) -> dict:
    timestamp = snapshot.get("asOf")
    age_seconds = None
    if timestamp:
        try:
            age_seconds = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)).total_seconds()))
        except ValueError:
            pass
    return {"asOf": timestamp, "ageSeconds": age_seconds}