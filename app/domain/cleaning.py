from datetime import date
from decimal import Decimal

from .errors import DataIntegrityError
from .fare import METRES_THRESHOLD
from .models import DataQualityNote, PayoutLine, Trip


def clean_trips(raw_rows: list[Trip]) -> tuple[list[Trip], list[DataQualityNote]]:
    notes = []
    seen: dict[str, Trip] = {}
    cleaned = []

    for row in raw_rows:
        # Check duplicate
        if row.trip_id in seen:
            prev = seen[row.trip_id]
            if prev != row:
                raise DataIntegrityError(f"Conflicting duplicate trip {row.trip_id}")
            notes.append(DataQualityNote(issue="exact_duplicate", trip_id=row.trip_id))
            continue

        seen[row.trip_id] = row

        # Check metres
        if row.distance_km >= METRES_THRESHOLD:
            notes.append(DataQualityNote(issue="distance_in_metres", trip_id=row.trip_id))
            row = Trip(
                trip_id=row.trip_id,
                rider_id=row.rider_id,
                started_at=row.started_at,
                status=row.status,
                distance_km=row.distance_km / Decimal(1000),
                surge_multiplier=row.surge_multiplier,
            )
            seen[row.trip_id] = row

        cleaned.append(row)

    return cleaned, notes


def clean_payouts(raw_rows: list[PayoutLine]) -> tuple[list[PayoutLine], list[DataQualityNote]]:
    notes = []
    seen: dict[tuple[str, str | None, date], PayoutLine] = {}
    cleaned = []

    for row in raw_rows:
        key = (row.rider_id, row.trip_id, row.payout_date)
        if key in seen:
            prev = seen[key]
            if prev == row:
                notes.append(DataQualityNote(issue="duplicate_payout", trip_id=row.trip_id))
                # Do NOT continue; keep the payout
            # Keep the first one? The prompt says "Some penalties are duplicated: same (rider, trip) has two cancellation_penalty lines. Only one is valid."
            if prev.line_type == row.line_type and prev.amount == row.amount:
                notes.append(DataQualityNote(issue="duplicate_payout", trip_id=row.trip_id))
                # Do NOT continue; keep the payout because it was actually charged/paid
        seen[key] = row
        cleaned.append(row)

    return cleaned, notes
