import json
import urllib.error
import urllib.request
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.payswift import (
    PaySwiftClient,
    PaySwiftRequest,
    PaySwiftValidationError,
)


@pytest.fixture
def client() -> PaySwiftClient:
    return PaySwiftClient("http://fake", timeout=1.0)


def create_mock_response(status_code: int, body: dict[str, Any]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def create_mock_http_error(status_code: int, body: dict[str, Any]) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://fake",
        code=status_code,
        msg="Error",
        hdrs=MagicMock(),
        fp=MagicMock(read=lambda: json.dumps(body).encode("utf-8")),
    )


@patch("urllib.request.urlopen")
def test_create_payment_success(mock_urlopen: MagicMock, client: PaySwiftClient) -> None:
    mock_urlopen.return_value = create_mock_response(
        201,
        {
            "payout_id": "pout_123",
            "rider_id": "R001",
            "amount": 100,
            "reference": "ref1",
            "status": "processed",
            "created_at": "2026-01-01T00:00:00Z",
        },
    )

    req = PaySwiftRequest(rider_id="R001", amount=100, reference="ref1")
    resp = client.create_payment(req, "idem1")

    assert resp.payout_id == "pout_123"
    assert resp.status == "processed"


@patch("urllib.request.urlopen")
def test_validation_error(mock_urlopen: MagicMock, client: PaySwiftClient) -> None:
    mock_urlopen.side_effect = create_mock_http_error(400, {"error": "invalid_amount"})

    req = PaySwiftRequest(rider_id="R001", amount=99999, reference="ref1")
    with pytest.raises(PaySwiftValidationError) as exc:
        client.create_payment(req, "idem1")

    assert "invalid_amount" in str(exc.value)


@patch("urllib.request.urlopen")
@patch("time.sleep", return_value=None)
def test_pay_safely_transient_retry(
    mock_sleep: MagicMock, mock_urlopen: MagicMock, client: PaySwiftClient
) -> None:
    # First call: 503 Service Unavailable -> transient error -> checks ledger (not found) -> retries -> 201 Success
    mock_urlopen.side_effect = [
        create_mock_http_error(503, {"error": "service_unavailable"}),  # POST /payouts
        create_mock_response(200, {"data": [], "count": 0}),  # GET /payouts (ledger)
        create_mock_response(
            201,
            {
                "payout_id": "pout_222",
                "rider_id": "R001",
                "amount": 100,
                "reference": "ref1",
                "status": "processed",
                "created_at": "2026-01-01",
            },
        ),  # POST /payouts
    ]

    req = PaySwiftRequest(rider_id="R001", amount=100, reference="ref1")
    res = client.pay_safely(req, "idem1")

    assert res.payout_id == "pout_222"
    assert mock_urlopen.call_count == 3


@patch("urllib.request.urlopen")
@patch("time.sleep", return_value=None)
def test_pay_safely_timeout_recovery(
    mock_sleep: MagicMock, mock_urlopen: MagicMock, client: PaySwiftClient
) -> None:
    # First call: Timeout!
    # The client must check the ledger. We mock the ledger to return the payment!
    # So it shouldn't retry POST, it should just return the result.

    timeout_err = urllib.error.URLError(TimeoutError("timed out"))

    mock_urlopen.side_effect = [
        timeout_err,  # POST /payouts (Timeout)
        create_mock_response(
            200,
            {
                "data": [
                    {
                        "payout_id": "pout_333",
                        "rider_id": "R002",
                        "amount": 100,
                        "reference": "ref2",
                        "status": "processed",
                        "created_at": "2026-01-01",
                    }
                ],
                "count": 1,
            },
        ),  # GET /payouts (Ledger)
    ]

    req = PaySwiftRequest(rider_id="R002", amount=100, reference="ref2")
    res = client.pay_safely(req, "idem2")

    assert res.payout_id == "pout_333"
    assert mock_urlopen.call_count == 2  # 1 POST, 1 GET. No second POST!


@patch("urllib.request.urlopen")
@patch("time.sleep", return_value=None)
def test_pay_safely_timeout_not_in_ledger(
    mock_sleep: MagicMock, mock_urlopen: MagicMock, client: PaySwiftClient
) -> None:
    # Timeout, but ledger is empty -> must retry POST
    timeout_err = urllib.error.URLError(TimeoutError("timed out"))

    mock_urlopen.side_effect = [
        timeout_err,  # POST /payouts (Timeout)
        create_mock_response(200, {"data": [], "count": 0}),  # GET /payouts (Ledger)
        create_mock_response(
            201,
            {
                "payout_id": "pout_444",
                "rider_id": "R003",
                "amount": 100,
                "reference": "ref3",
                "status": "processed",
                "created_at": "2026-01-01",
            },
        ),  # POST /payouts (Retry)
    ]

    req = PaySwiftRequest(rider_id="R003", amount=100, reference="ref3")
    res = client.pay_safely(req, "idem3")

    assert res.payout_id == "pout_444"
    assert mock_urlopen.call_count == 3
