from collections import defaultdict
from datetime import date, datetime
from typing import Protocol

from .fare import (
    CANCEL_PENALTY,
    DISPUTE_WINDOW_DAYS,
    INCENTIVE_AMOUNT,
    INCENTIVE_MIN_TRIPS,
    compute_trip_fare,
)
from .models import DaySummary, Discrepancy, DiscrepancyKind, LineType, PayoutLine, Trip, TripStatus
from .timeutil import to_ist_date


class TripRepository(Protocol):
    def get_by_rider(self, rider_id: str) -> list[Trip]: ...
    def get_trip(self, rider_id: str, trip_id: str) -> Trip: ...


class PayoutRepository(Protocol):
    def get_by_rider(self, rider_id: str) -> list[PayoutLine]: ...


class ReconciliationService:
    def __init__(self, trips: TripRepository, payouts: PayoutRepository) -> None:
        self.trips = trips
        self.payouts = payouts

    def find_discrepancies(
        self, rider_id: str, *, as_of: datetime, day: date | None = None, trip_id: str | None = None
    ) -> list[Discrepancy]:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")

        as_of_ist = to_ist_date(as_of)

        trips = self.trips.get_by_rider(rider_id)
        if trip_id is not None:
            # ensure it exists and belongs to this rider (will raise TripNotFoundError if not)
            self.trips.get_trip(rider_id, trip_id)
            trips = [t for t in trips if t.trip_id == trip_id]

        if day is not None:
            trips = [t for t in trips if to_ist_date(t.started_at) == day]

        payouts = self.payouts.get_by_rider(rider_id)

        trips_by_day = defaultdict(list)
        for t in trips:
            trips_by_day[to_ist_date(t.started_at)].append(t)

        payouts_by_day = defaultdict(list)
        for p in payouts:
            # We map payouts by their payout_date
            # The prompt says: "payout_date always equals the IST date of the trip."
            payouts_by_day[p.payout_date].append(p)

        discrepancies: list[Discrepancy] = []

        # We must iterate over all days that have either trips or payouts for this rider
        # constrained by the requested day (if provided)
        all_days = set(trips_by_day.keys()) | set(payouts_by_day.keys())
        if day is not None:
            all_days = {day}

        for d in all_days:
            within_window = (as_of_ist - d).days <= DISPUTE_WINDOW_DAYS and d <= as_of_ist

            day_trips = trips_by_day.get(d, [])
            day_payouts = payouts_by_day.get(d, [])

            # Map payouts by trip
            payouts_by_trip = defaultdict(list)
            for p in day_payouts:
                if p.trip_id:
                    payouts_by_trip[p.trip_id].append(p)

            # 1. Process Trips (fares and penalties)
            completed_count = 0
            for t in day_trips:
                if t.status == TripStatus.COMPLETED:
                    completed_count += 1
                    owed = compute_trip_fare(t.distance_km, t.surge_multiplier)

                    trip_pays = [
                        p
                        for p in payouts_by_trip.get(t.trip_id, [])
                        if p.line_type == LineType.TRIP
                    ]
                    paid = sum(p.amount for p in trip_pays)

                    if owed > paid:
                        claimable = max(0, owed - paid)
                        kind = (
                            DiscrepancyKind.TRIP_UNPAID
                            if paid == 0
                            else DiscrepancyKind.TRIP_UNDERPAID
                        )
                        discrepancies.append(
                            Discrepancy(
                                kind=kind,
                                rider_id=rider_id,
                                day=d,
                                trip_id=t.trip_id,
                                owed=owed,
                                paid=paid,
                                claimable=claimable,
                                within_window=within_window,
                                detail={
                                    "distance_km": float(t.distance_km),
                                    "surge": float(t.surge_multiplier),
                                },
                            )
                        )

                elif t.status == TripStatus.CANCELLED_BY_RIDER:
                    owed = -CANCEL_PENALTY
                    trip_pays = [
                        p
                        for p in payouts_by_trip.get(t.trip_id, [])
                        if p.line_type == LineType.CANCELLATION_PENALTY
                    ]
                    paid = sum(p.amount for p in trip_pays)

                    if paid < owed:  # e.g. paid -20, owed -10 -> they were charged 10 too much
                        claimable = owed - paid
                        discrepancies.append(
                            Discrepancy(
                                kind=DiscrepancyKind.DUPLICATE_PENALTY,
                                rider_id=rider_id,
                                day=d,
                                trip_id=t.trip_id,
                                owed=owed,
                                paid=paid,
                                claimable=claimable,
                                within_window=within_window,
                                detail={},
                            )
                        )
                    elif paid == owed:
                        discrepancies.append(
                            Discrepancy(
                                kind=DiscrepancyKind.PENALTY_VALID,
                                rider_id=rider_id,
                                day=d,
                                trip_id=t.trip_id,
                                owed=owed,
                                paid=paid,
                                claimable=0,
                                within_window=within_window,
                                detail={},
                            )
                        )

            # 2. Process Incentives
            if trip_id is None:  # Only if they aren't querying a specific trip
                # we need the real completed count for the day, which might require querying the repository
                # if the user queried by day, we already have it. If by trip, we skip it.
                # Since day_trips might be filtered by trip_id, we should fetch all trips for the day to be safe.
                # But actually, earlier we filtered the *rider's* trips by `trip_id`. So day_trips is incomplete.
                pass

        # To calculate incentives safely, we shouldn't rely on the filtered trips.
        # Let's do a separate pass for incentives for the relevant days.
        days_to_check_incentives = all_days if trip_id is None else set()

        # We need ALL trips for the rider to do incentives correctly
        all_rider_trips = self.trips.get_by_rider(rider_id)
        all_trips_by_day = defaultdict(list)
        for t in all_rider_trips:
            all_trips_by_day[to_ist_date(t.started_at)].append(t)

        for d in days_to_check_incentives:
            within_window = (as_of_ist - d).days <= DISPUTE_WINDOW_DAYS and d <= as_of_ist
            completed = sum(1 for t in all_trips_by_day[d] if t.status == TripStatus.COMPLETED)

            day_payouts = [p for p in payouts if p.payout_date == d]
            inc_pays = [p for p in day_payouts if p.line_type == LineType.DAILY_INCENTIVE]
            paid = sum(p.amount for p in inc_pays)

            owed = INCENTIVE_AMOUNT if completed >= INCENTIVE_MIN_TRIPS else 0

            if owed > paid:
                discrepancies.append(
                    Discrepancy(
                        kind=DiscrepancyKind.INCENTIVE_MISSING,
                        rider_id=rider_id,
                        day=d,
                        trip_id=None,
                        owed=owed,
                        paid=paid,
                        claimable=owed - paid,
                        within_window=within_window,
                        detail={"completed_count": completed},
                    )
                )
            elif paid > owed:
                discrepancies.append(
                    Discrepancy(
                        kind=DiscrepancyKind.INCENTIVE_OVERPAID,
                        rider_id=rider_id,
                        day=d,
                        trip_id=None,
                        owed=owed,
                        paid=paid,
                        claimable=0,
                        within_window=within_window,
                        detail={"completed_count": completed},
                    )
                )

        # Sort the results by day, then trip_id
        def sort_key(disc: Discrepancy) -> tuple[date, str]:
            return (disc.day, disc.trip_id or "")

        discrepancies.sort(key=sort_key)
        return discrepancies

    def day_summary(self, rider_id: str, day: date) -> DaySummary:
        trips = [t for t in self.trips.get_by_rider(rider_id) if to_ist_date(t.started_at) == day]
        payouts = [p for p in self.payouts.get_by_rider(rider_id) if p.payout_date == day]

        completed_count = sum(1 for t in trips if t.status == TripStatus.COMPLETED)

        owed_trips = sum(
            compute_trip_fare(t.distance_km, t.surge_multiplier)
            for t in trips
            if t.status == TripStatus.COMPLETED
        )
        paid_trips = sum(p.amount for p in payouts if p.line_type == LineType.TRIP)

        pen_owed = sum(-CANCEL_PENALTY for t in trips if t.status == TripStatus.CANCELLED_BY_RIDER)
        pen_paid = sum(p.amount for p in payouts if p.line_type == LineType.CANCELLATION_PENALTY)

        inc_owed = INCENTIVE_AMOUNT if completed_count >= INCENTIVE_MIN_TRIPS else 0
        inc_paid = sum(p.amount for p in payouts if p.line_type == LineType.DAILY_INCENTIVE)

        return DaySummary(
            completed_trip_count=completed_count,
            owed_total=owed_trips + pen_owed + inc_owed,
            paid_total=paid_trips + pen_paid + inc_paid,
            incentive_owed=inc_owed,
            incentive_paid=inc_paid,
            penalties_owed=pen_owed,
            penalties_paid=pen_paid,
        )
