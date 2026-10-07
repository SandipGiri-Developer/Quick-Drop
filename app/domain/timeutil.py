from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def parse_utc(ts: str) -> datetime:
    if not ts.endswith("Z"):
        raise ValueError(f"Expected UTC time ending with Z, got {ts}")
    return datetime.fromisoformat(ts)


def to_ist_date(utc_dt: datetime) -> date:
    if utc_dt.tzinfo is None:
        raise ValueError("Expected timezone-aware datetime")
    return utc_dt.astimezone(IST).date()
