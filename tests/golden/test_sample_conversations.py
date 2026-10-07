from pathlib import Path

import pytest

from app.data.loader import load_dataset
from app.domain.errors import TripNotFoundError
from app.domain.models import DiscrepancyKind, PayoutLine, Trip
from app.domain.reconciliation import ReconciliationService
from app.domain.timeutil import parse_utc


class InMemoryTripRepository:
    def __init__(self, trips: list[Trip]) -> None:
        self.trips = trips

    def get_by_rider(self, rider_id: str) -> list[Trip]:
        return [t for t in self.trips if t.rider_id == rider_id]

    def get_trip(self, rider_id: str, trip_id: str) -> Trip:
        for t in self.trips:
            if t.trip_id == trip_id:
                if t.rider_id != rider_id:
                    raise TripNotFoundError(f"Trip {trip_id} not found for rider {rider_id}")
                return t
        raise TripNotFoundError(f"Trip {trip_id} not found")


class InMemoryPayoutRepository:
    def __init__(self, payouts: list[PayoutLine]) -> None:
        self.payouts = payouts

    def get_by_rider(self, rider_id: str) -> list[PayoutLine]:
        return [p for p in self.payouts if p.rider_id == rider_id]


@pytest.fixture(scope="module")
def service() -> ReconciliationService:
    ds = load_dataset(Path("data"))
    return ReconciliationService(
        trips=InMemoryTripRepository(ds.trips), payouts=InMemoryPayoutRepository(ds.payouts)
    )


def test_golden_r003(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")  # 12:00 IST
    discs = service.find_discrepancies("R003", as_of=as_of, trip_id="T926334")
    assert len(discs) == 1
    d = discs[0]
    assert d.claimable == 25
    assert d.kind == DiscrepancyKind.TRIP_UNDERPAID


def test_golden_r007(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    discs = service.find_discrepancies("R007", as_of=as_of, trip_id="T840677")
    assert len(discs) == 1
    assert discs[0].claimable == 34


def test_golden_r031(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    discs = service.find_discrepancies("R031", as_of=as_of, trip_id="T312538")
    assert len(discs) == 1
    assert discs[0].claimable == 22


def test_golden_r026(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    discs = service.find_discrepancies("R026", as_of=as_of, trip_id="T672899")
    assert len(discs) == 1
    assert discs[0].claimable == 32


def test_golden_r027(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    discs = service.find_discrepancies("R027", as_of=as_of)
    trip_disc = next(d for d in discs if d.trip_id == "T604546")
    pen_disc = next(d for d in discs if d.trip_id == "T936237")

    assert trip_disc.claimable == 15
    assert pen_disc.claimable == 10
    assert pen_disc.kind == DiscrepancyKind.DUPLICATE_PENALTY


def test_golden_out_of_window(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    discs = service.find_discrepancies("R022", as_of=as_of, trip_id="T502951")
    assert len(discs) == 1
    assert discs[0].within_window is False


def test_golden_incentive_missing_r005(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    from datetime import date

    discs = service.find_discrepancies("R005", as_of=as_of, day=date(2026, 9, 21))
    inc_discs = [d for d in discs if d.kind == DiscrepancyKind.INCENTIVE_MISSING]
    assert len(inc_discs) == 1
    assert inc_discs[0].claimable == 150


def test_golden_incentive_not_owed_r025(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    from datetime import date

    discs = service.find_discrepancies("R025", as_of=as_of, day=date(2026, 9, 19))
    inc_discs = [
        d
        for d in discs
        if d.kind in (DiscrepancyKind.INCENTIVE_MISSING, DiscrepancyKind.INCENTIVE_OVERPAID)
    ]
    assert len(inc_discs) == 0


def test_golden_multiple_unpaid_r016(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    from datetime import date

    discs = service.find_discrepancies("R016", as_of=as_of, day=date(2026, 9, 19))
    unpaid = [d for d in discs if d.kind == DiscrepancyKind.TRIP_UNPAID]
    assert len(unpaid) == 5
    assert sum(d.claimable for d in unpaid) == 425


def test_golden_ownership(service: ReconciliationService) -> None:
    as_of = parse_utc("2026-09-23T06:30:00Z")
    with pytest.raises(TripNotFoundError):
        service.find_discrepancies("R021", as_of=as_of, trip_id="T482410")
