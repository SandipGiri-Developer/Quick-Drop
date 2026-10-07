from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.cleaning import clean_payouts, clean_trips
from app.domain.errors import DataIntegrityError
from app.domain.models import LineType, PayoutLine, Trip, TripStatus


def test_clean_trips_metres() -> None:
    t = Trip(
        trip_id="T1",
        rider_id="R001",
        started_at=datetime.now(UTC),
        status=TripStatus.COMPLETED,
        distance_km=Decimal("150.0"),
        surge_multiplier=Decimal("1.0"),
    )
    cleaned, notes = clean_trips([t])
    assert len(cleaned) == 1
    assert cleaned[0].distance_km == Decimal("0.150")
    assert notes[0].issue == "distance_in_metres"


def test_clean_trips_duplicate_exact() -> None:
    t = Trip(
        trip_id="T1",
        rider_id="R001",
        started_at=datetime.now(UTC),
        status=TripStatus.COMPLETED,
        distance_km=Decimal("5.0"),
        surge_multiplier=Decimal("1.0"),
    )
    cleaned, notes = clean_trips([t, t])
    assert len(cleaned) == 1
    assert notes[0].issue == "exact_duplicate"


def test_clean_trips_duplicate_conflict() -> None:
    t1 = Trip(
        trip_id="T1",
        rider_id="R001",
        started_at=datetime.now(UTC),
        status=TripStatus.COMPLETED,
        distance_km=Decimal("5.0"),
        surge_multiplier=Decimal("1.0"),
    )
    t2 = Trip(
        trip_id="T1",
        rider_id="R001",
        started_at=datetime.now(UTC),
        status=TripStatus.COMPLETED,
        distance_km=Decimal("6.0"),
        surge_multiplier=Decimal("1.0"),
    )
    with pytest.raises(DataIntegrityError):
        clean_trips([t1, t2])


def test_clean_payouts_duplicate_penalty() -> None:
    p1 = PayoutLine(
        line_id="L1",
        payout_date=date(2026, 9, 20),
        rider_id="R001",
        line_type=LineType.CANCELLATION_PENALTY,
        trip_id="T1",
        amount=-10,
    )
    p2 = PayoutLine(
        line_id="L2",
        payout_date=date(2026, 9, 20),
        rider_id="R001",
        line_type=LineType.CANCELLATION_PENALTY,
        trip_id="T1",
        amount=-10,
    )
    cleaned, notes = clean_payouts([p1, p2])
    assert len(cleaned) == 2
    assert len(notes) == 1
    assert notes[0].issue == "duplicate_payout"
