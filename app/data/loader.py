import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..domain.cleaning import clean_payouts, clean_trips
from ..domain.errors import DataIntegrityError
from ..domain.models import DataQualityNote, LineType, PayoutLine, Rider, Trip, TripStatus
from ..domain.rider_id import normalize_rider_id
from ..domain.timeutil import parse_utc


@dataclass
class Dataset:
    riders: list[Rider]
    trips: list[Trip]
    payouts: list[PayoutLine]
    notes: list[DataQualityNote]


def load_dataset(data_dir: Path) -> Dataset:
    notes: list[DataQualityNote] = []

    # Load Riders
    riders = []
    with open(data_dir / "riders.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                r_id = normalize_rider_id(row["rider_id"].strip())
                riders.append(
                    Rider(
                        rider_id=r_id,
                        name=row["name"].strip(),
                        city=row["city"].strip(),
                        joined_on=date.fromisoformat(row["joined_on"].strip()),
                    )
                )
            except Exception as e:  # noqa: BLE001
                raise DataIntegrityError(f"Row {i} in riders.csv malformed: {e}")

    # Load Trips
    raw_trips = []
    with open(data_dir / "trips.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                raw_trips.append(
                    Trip(
                        trip_id=row["trip_id"].strip(),
                        rider_id=normalize_rider_id(row["rider_id"].strip()),
                        started_at=parse_utc(row["started_at"].strip()),
                        status=TripStatus(row["status"].strip()),
                        distance_km=Decimal(row["distance_km"].strip()),
                        surge_multiplier=Decimal(row["surge_multiplier"].strip()),
                    )
                )
            except Exception as e:  # noqa: BLE001
                raise DataIntegrityError(f"Row {i} in trips.csv malformed: {e}")

    cleaned_trips, trip_notes = clean_trips(raw_trips)
    notes.extend(trip_notes)

    # Load Payouts
    raw_payouts = []
    with open(data_dir / "payout_lines.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                trip_id = row["trip_id"].strip()
                raw_payouts.append(
                    PayoutLine(
                        line_id=row["line_id"].strip(),
                        payout_date=date.fromisoformat(row["payout_date"].strip()),
                        rider_id=normalize_rider_id(row["rider_id"].strip()),
                        line_type=LineType(row["line_type"].strip()),
                        trip_id=trip_id if trip_id else None,
                        amount=int(row["amount"].strip()),
                    )
                )
            except Exception as e:  # noqa: BLE001
                raise DataIntegrityError(f"Row {i} in payout_lines.csv malformed: {e}")

    cleaned_payouts, pay_notes = clean_payouts(raw_payouts)
    notes.extend(pay_notes)

    return Dataset(riders=riders, trips=cleaned_trips, payouts=cleaned_payouts, notes=notes)


_global_dataset = None


def get_cached_dataset() -> Dataset:
    global _global_dataset
    if _global_dataset is None:
        _global_dataset = load_dataset(Path("data"))
    return _global_dataset


class CsvTripRepository:
    def __init__(self) -> None:
        self.dataset = get_cached_dataset()

    def get_by_rider(self, rider_id: str) -> list[Trip]:
        return [t for t in self.dataset.trips if t.rider_id == rider_id]

    def get_trip(self, rider_id: str, trip_id: str) -> Trip:
        from ..domain.errors import TripNotFoundError

        for t in self.dataset.trips:
            if t.trip_id == trip_id:
                if t.rider_id != rider_id:
                    raise TripNotFoundError(f"Trip {trip_id} not found for rider {rider_id}")
                return t
        raise TripNotFoundError(f"Trip {trip_id} not found")


class CsvPayoutRepository:
    def __init__(self) -> None:
        self.dataset = get_cached_dataset()

    def get_by_rider(self, rider_id: str) -> list[PayoutLine]:
        return [p for p in self.dataset.payouts if p.rider_id == rider_id]
