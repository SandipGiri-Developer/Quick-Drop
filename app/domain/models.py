from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .money import Rupees


class TripStatus(Enum):
    COMPLETED = "completed"
    CANCELLED_BY_CUSTOMER = "cancelled_by_customer"
    CANCELLED_BY_RIDER = "cancelled_by_rider"


class LineType(Enum):
    TRIP = "trip"
    DAILY_INCENTIVE = "daily_incentive"
    CANCELLATION_PENALTY = "cancellation_penalty"


@dataclass(frozen=True, slots=True)
class Trip:
    trip_id: str
    rider_id: str
    started_at: datetime
    status: TripStatus
    distance_km: Decimal
    surge_multiplier: Decimal


@dataclass(frozen=True, slots=True)
class PayoutLine:
    line_id: str
    payout_date: date
    rider_id: str
    line_type: LineType
    trip_id: str | None
    amount: Rupees


@dataclass(frozen=True, slots=True)
class Rider:
    rider_id: str
    name: str
    city: str
    joined_on: date


class DiscrepancyKind(Enum):
    TRIP_UNDERPAID = "TRIP_UNDERPAID"
    TRIP_UNPAID = "TRIP_UNPAID"
    DUPLICATE_PENALTY = "DUPLICATE_PENALTY"
    INCENTIVE_MISSING = "INCENTIVE_MISSING"
    INCENTIVE_OVERPAID = "INCENTIVE_OVERPAID"
    PENALTY_VALID = "PENALTY_VALID"


@dataclass(frozen=True, slots=True)
class Discrepancy:
    kind: DiscrepancyKind
    rider_id: str
    day: date
    trip_id: str | None
    owed: Rupees
    paid: Rupees
    claimable: Rupees
    within_window: bool
    detail: dict[str, str | int | float]


@dataclass(frozen=True, slots=True)
class DataQualityNote:
    issue: str
    row_number: int | None = None
    trip_id: str | None = None


@dataclass(frozen=True, slots=True)
class DaySummary:
    completed_trip_count: int
    owed_total: Rupees
    paid_total: Rupees
    incentive_owed: Rupees
    incentive_paid: Rupees
    penalties_owed: Rupees
    penalties_paid: Rupees
