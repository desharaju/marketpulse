from datetime import datetime, timezone

import httpx
import pytest

from app.providers.market import FinnhubProvider


def test_finnhub_quote_normalizes_fields_without_claiming_premarket_data():
    observed_at = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    bar_time = int(datetime(2025, 1, 6, 14, 30, tzinfo=timezone.utc).timestamp())
    row = FinnhubProvider._normalize(
        "ACME",
        {"c": 10.5, "d": 0.5, "dp": 5.0, "t": int(observed_at.timestamp())},
        {"s": "ok", "t": [bar_time], "v": [1200]},
        observed_at,
    )

    assert row["symbol"] == "ACME"
    assert row["price"] == 10.5
    assert row["volume"] == 1200
    assert row["dollarVolume"] == 12600
    assert row["relativeVolume"] is None
    assert row["premarket"] is None
    assert row["simulated"] is False
    assert row["source"] == "Finnhub"


def test_finnhub_rejects_missing_or_invalid_quote():
    with pytest.raises(ValueError, match="Quote unavailable"):
        FinnhubProvider._normalize("ACME", {"c": 0}, {"s": "no_data"}, datetime.now(timezone.utc))


def test_finnhub_quote_remains_usable_without_candle_access():
    observed_at = datetime(2025, 1, 6, 15, 0, tzinfo=timezone.utc)
    row = FinnhubProvider._normalize(
        "ACME",
        {"c": 10.5, "d": 0.5, "dp": 5.0, "t": int(observed_at.timestamp())},
        None,
        observed_at,
    )

    assert row["price"] == 10.5
    assert row["volume"] is None
    assert row["averageVolume"] is None
    assert row["relativeVolume"] is None
    assert row["dollarVolume"] is None
    assert row["simulated"] is False


@pytest.mark.asyncio
async def test_finnhub_candle_permission_failure_does_not_discard_quote(monkeypatch):
    provider = FinnhubProvider("test-token")
    candle_requests = 0

    async def fake_get(_client, path, _params):
        nonlocal candle_requests
        if path == "quote":
            return {"c": 10.5, "d": 0.5, "dp": 5.0, "t": 1_736_178_000}
        candle_requests += 1
        request = httpx.Request("GET", "https://finnhub.io/api/v1/stock/candle")
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    monkeypatch.setattr(provider, "_get", fake_get)
    snapshot = await provider.fetch_stocks(["ACME", "BETA", "GAMMA"])

    assert [item["symbol"] for item in snapshot["items"]] == ["ACME", "BETA", "GAMMA"]
    assert all(item["price"] == 10.5 for item in snapshot["items"])
    assert all(item["volume"] is None for item in snapshot["items"])
    assert all("HTTP 403" in item["volumeUnavailableReason"] for item in snapshot["items"])
    assert not snapshot["errors"]
    assert any("without volume-derived fields" in item for item in snapshot["limitations"])
    assert candle_requests == 1


@pytest.mark.asyncio
async def test_finnhub_loads_and_caches_first_30_directory_symbols(monkeypatch):
    provider = FinnhubProvider("test-token")
    calls = 0

    async def fake_get(_client, path, _params):
        nonlocal calls
        assert path == "stock/symbol"
        calls += 1
        return [{"displaySymbol": f"TICKER{index}"} for index in range(35)]

    monkeypatch.setattr(provider, "_get", fake_get)
    symbols = await provider.fetch_symbols(limit=100)
    cached_symbols = await provider.fetch_symbols(limit=5)

    assert len(symbols) == 30
    assert symbols[0] == "TICKER0"
    assert symbols[-1] == "TICKER29"
    assert cached_symbols == symbols[:5]
    assert calls == 1


def test_provider_error_messages_do_not_echo_credentials_or_urls():
    provider = FinnhubProvider("test-token")
    assert provider._safe_error(TimeoutError("token=test-token")) == "Provider response could not be normalized"