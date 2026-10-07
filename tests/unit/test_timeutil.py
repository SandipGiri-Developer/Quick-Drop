from datetime import UTC, datetime

import pytest

from app.domain.timeutil import parse_utc, to_ist_date


def test_parse_utc() -> None:
    dt = parse_utc("2026-09-20T20:00:00Z")
    assert dt.tzinfo == UTC
    assert dt.hour == 20

    with pytest.raises(ValueError):
        parse_utc("2026-09-20T20:00:00")


def test_to_ist_date() -> None:
    # 20:00 UTC is 01:30 IST next day
    dt = parse_utc("2026-09-20T20:00:00Z")
    assert str(to_ist_date(dt)) == "2026-09-21"

    # Boundary 18:29:59Z is 23:59:59 IST (same day)
    dt1 = parse_utc("2026-09-20T18:29:59Z")
    assert str(to_ist_date(dt1)) == "2026-09-20"

    # Boundary 18:30:00Z is 00:00:00 IST (next day)
    dt2 = parse_utc("2026-09-20T18:30:00Z")
    assert str(to_ist_date(dt2)) == "2026-09-21"


def test_to_ist_date_rejects_naive() -> None:
    with pytest.raises(ValueError):
        to_ist_date(datetime(2026, 9, 20))  # noqa: DTZ001
