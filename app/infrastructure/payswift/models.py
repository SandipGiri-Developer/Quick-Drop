from dataclasses import dataclass
from enum import Enum


class PayoutStatus(Enum):
    PROCESSED = "processed"
    FAILED = "failed"
    PENDING = "pending"


@dataclass(frozen=True)
class PaySwiftRequest:
    rider_id: str
    amount: int
    reference: str


@dataclass(frozen=True)
class PaySwiftResponse:
    payout_id: str
    rider_id: str
    amount: int
    reference: str
    status: str
    created_at: str


@dataclass(frozen=True)
class PaySwiftLedgerResponse:
    data: list[PaySwiftResponse]
    count: int


@dataclass(frozen=True)
class PaymentResult:
    payout_id: str
    status: PayoutStatus
    rider_id: str
    amount: int
    reference: str
