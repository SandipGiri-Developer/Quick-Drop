import uuid

import pytest

from app.core.config import settings
from app.infrastructure.payswift import (
    PaymentResult,
    PayoutStatus,
    PaySwiftClient,
    PaySwiftConflictError,
    PaySwiftRequest,
    PaySwiftValidationError,
)


@pytest.fixture
def client() -> PaySwiftClient:
    return PaySwiftClient(settings.payswift_base_url, timeout=10.0)


def test_payswift_successful_payment(client: PaySwiftClient) -> None:
    idem_key = str(uuid.uuid4())
    req = PaySwiftRequest(rider_id="R100", amount=120, reference=f"integration_test_{idem_key}")

    result = client.pay_safely(req, idem_key)
    assert result.status == PayoutStatus.PROCESSED
    assert result.amount == 120
    assert result.rider_id == "R100"

    # Check ledger
    ledger = client.get_ledger("R100")
    assert any(p.payout_id == result.payout_id for p in ledger.data)


def test_payswift_idempotency_same_body(client: PaySwiftClient) -> None:
    idem_key = str(uuid.uuid4())
    req = PaySwiftRequest(rider_id="R101", amount=150, reference=f"idem_test_{idem_key}")

    res1 = client.pay_safely(req, idem_key)
    res2 = client.pay_safely(req, idem_key)

    assert res1.payout_id == res2.payout_id


def test_payswift_idempotency_conflict(client: PaySwiftClient) -> None:
    idem_key = str(uuid.uuid4())
    req1 = PaySwiftRequest(rider_id="R102", amount=100, reference=f"conflict_{idem_key}")
    client.pay_safely(req1, idem_key)

    req2 = PaySwiftRequest(rider_id="R102", amount=150, reference=f"conflict_{idem_key}")
    with pytest.raises(PaySwiftConflictError):
        client.pay_safely(req2, idem_key)


def test_payswift_validation_error(client: PaySwiftClient) -> None:
    idem_key = str(uuid.uuid4())
    # amount > 10000 causes validation error in sandbox
    req = PaySwiftRequest(rider_id="R103", amount=15000, reference="too_large")
    with pytest.raises(PaySwiftValidationError):
        client.pay_safely(req, idem_key)


def test_payswift_50_payment_gate(client: PaySwiftClient) -> None:
    """
    Sends 50 legitimate payment requests through the client.
    The acceptance condition is exactly 50 corresponding PaySwift ledger entries.
    """
    rider_id = f"R999_{uuid.uuid4().hex[:6]}"

    # First, get baseline count
    baseline = client.get_ledger(rider_id).count

    results: list[PaymentResult] = []

    # Fire 50 payments
    run_id = str(uuid.uuid4())
    for i in range(50):
        idem_key = f"gate_50_{run_id}_{i}"
        req = PaySwiftRequest(rider_id=rider_id, amount=100 + i, reference=f"gate_{run_id}_{i}")
        res = client.pay_safely(req, idem_key)
        results.append(res)

    # Check ledger
    final_ledger = client.get_ledger(rider_id)
    assert final_ledger.count == baseline + 50

    # Ensure no duplicates in our results
    payout_ids = {r.payout_id for r in results}
    assert len(payout_ids) == 50

    # Ensure all payout IDs exist in the ledger
    ledger_payout_ids = {p.payout_id for p in final_ledger.data}
    assert payout_ids.issubset(ledger_payout_ids)
