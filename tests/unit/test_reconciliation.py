from datetime import datetime

import pytest

from app.domain.errors import TripNotFoundError
from app.domain.models import PayoutLine, Trip
from app.domain.reconciliation import ReconciliationService


class DummyTripRepo:
    def get_by_rider(self, r: str) -> list[Trip]:
        return []

    def get_trip(self, r: str, t: str) -> Trip:
        raise TripNotFoundError()


class DummyPayoutRepo:
    def get_by_rider(self, r: str) -> list[PayoutLine]:
        return []


def test_naive_as_of_rejected() -> None:
    service = ReconciliationService(DummyTripRepo(), DummyPayoutRepo())
    with pytest.raises(ValueError):
        service.find_discrepancies("R001", as_of=datetime(2026, 9, 23))  # noqa: DTZ001
