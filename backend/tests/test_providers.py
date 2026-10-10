from datetime import datetime, timezone

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


def test_provider_error_messages_do_not_echo_credentials_or_urls():
    provider = FinnhubProvider("test-token")
    assert provider._safe_error(TimeoutError("token=test-token")) == "Provider response could not be normalized"