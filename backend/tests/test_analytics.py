from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.analytics import intraday_relative_volume, market_session, ranking_score, trading_day


def test_relative_volume_compares_matching_clock_intervals():
    current = [{"timestamp": datetime(2025, 1, 6, 10, 0, tzinfo=ZoneInfo("America/New_York")), "volume": 300}]
    history = [
        [{"timestamp": datetime(2025, 1, day, 10, 0, tzinfo=ZoneInfo("America/New_York")), "volume": 100}]
        for day in (2, 3, 4)
    ]
    result = intraday_relative_volume(current, history)
    assert result["relativeVolume"] == 3
    assert result["fullDayEstimate"] == 3
    assert result["baselineSessions"] == 3


def test_relative_volume_requires_multiple_baseline_sessions():
    assert intraday_relative_volume([], [])["relativeVolume"] is None
    current = [{"timestamp": datetime(2025, 1, 6, 10, tzinfo=ZoneInfo("America/New_York")), "volume": 500}]
    history = [[{"timestamp": current[0]["timestamp"], "volume": 100}]]
    assert intraday_relative_volume(current, history)["fullDayEstimate"] is None


def test_ranking_is_bounded_and_ignores_missing_signals():
    ranked = ranking_score({"relativeVolume": 10, "changePercent": None, "dollarVolume": None, "catalyst": None})
    assert ranked["score"] == 100
    assert ranked["signalsAvailable"] == ["relativeVolume"]


def test_market_calendar_accounts_for_weekends_holidays_and_early_close():
    assert trading_day(date(2025, 1, 20)) is False
    assert market_session(datetime(2025, 1, 6, 8, 0, tzinfo=ZoneInfo("America/New_York")))["status"] == "premarket"
    early_close = market_session(datetime(2025, 11, 28, 13, 30, tzinfo=ZoneInfo("America/New_York")))
    assert early_close["status"] == "after-hours"