from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas_market_calendars as market_calendars

NEW_YORK = ZoneInfo("America/New_York")


def market_session(now: datetime | None = None) -> dict[str, str | bool]:
    current = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    calendar = market_calendars.get_calendar("NYSE")
    schedule = calendar.schedule(start_date=current.date(), end_date=current.date())
    if schedule.empty:
        return {"status": "closed", "isTradingDay": False, "timezone": "America/New_York"}

    opening = schedule.iloc[0]["market_open"].to_pydatetime().astimezone(NEW_YORK)
    closing = schedule.iloc[0]["market_close"].to_pydatetime().astimezone(NEW_YORK)
    premarket = opening.replace(hour=4, minute=0)
    after_hours = closing.replace(hour=20, minute=0)
    if current < premarket or current >= after_hours:
        status = "closed"
    elif current < opening:
        status = "premarket"
    elif current < closing:
        status = "regular"
    else:
        status = "after-hours"
    return {
        "status": status,
        "isTradingDay": True,
        "timezone": "America/New_York",
        "marketOpen": opening.isoformat(),
        "marketClose": closing.isoformat(),
    }


def intraday_relative_volume(
    current_bars: list[dict], historical_sessions: list[list[dict]],
) -> dict[str, float | int | None]:
    """Compare cumulative current volume to the same clock-time interval on prior sessions."""
    if not current_bars or len(historical_sessions) < 2:
        return {"relativeVolume": None, "fullDayEstimate": None, "baselineSessions": len(historical_sessions)}

    current_bars = sorted(current_bars, key=lambda bar: bar["timestamp"])
    cutoff = current_bars[-1]["timestamp"]
    current_volume = sum(max(0, bar["volume"]) for bar in current_bars if bar["timestamp"] <= cutoff)
    comparable = []
    day_totals = []
    for session in historical_sessions:
        session = sorted(session, key=lambda bar: bar["timestamp"])
        day_totals.append(sum(max(0, bar["volume"]) for bar in session))
        comparable.append(sum(max(0, bar["volume"]) for bar in session if bar["timestamp"].time() <= cutoff.time()))

    comparable_average = sum(comparable) / len(comparable)
    daily_average = sum(day_totals) / len(day_totals)
    if comparable_average <= 0 or daily_average <= 0:
        return {"relativeVolume": None, "fullDayEstimate": None, "baselineSessions": len(historical_sessions)}

    relative_volume = current_volume / comparable_average
    return {
        "relativeVolume": round(relative_volume, 2),
        "fullDayEstimate": round(relative_volume, 2),
        "baselineSessions": len(historical_sessions),
    }


def ranking_score(signals: dict[str, float | None], weights: dict[str, float] | None = None) -> dict:
    """Weighted, bounded score. Missing signals do not count as zero evidence."""
    weights = weights or {"relativeVolume": 0.4, "changePercent": 0.3, "dollarVolume": 0.2, "catalyst": 0.1}
    normalized = {
        "relativeVolume": min(max((signals.get("relativeVolume") or 0) / 5, 0), 1),
        "changePercent": min(abs(signals.get("changePercent") or 0) / 10, 1),
        "dollarVolume": min((signals.get("dollarVolume") or 0) / 100_000_000, 1),
        "catalyst": min(max(signals.get("catalyst") or 0, 0), 1),
    }
    available = [key for key in weights if signals.get(key) is not None]
    total_weight = sum(weights[key] for key in available)
    score = sum(normalized[key] * weights[key] for key in available) / total_weight if total_weight else 0
    return {"score": round(score * 100, 1), "breakdown": normalized, "signalsAvailable": available}


def trading_day(value: date) -> bool:
    return not market_calendars.get_calendar("NYSE").schedule(start_date=value, end_date=value).empty