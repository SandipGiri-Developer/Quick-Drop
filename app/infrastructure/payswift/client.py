import json
import logging
import urllib.error
import urllib.request
from typing import Any, Protocol

from .errors import (
    PaySwiftAuthenticationError,
    PaySwiftConflictError,
    PaySwiftError,
    PaySwiftNotFoundError,
    PaySwiftProtocolError,
    PaySwiftRateLimitError,
    PaySwiftTimeoutError,
    PaySwiftTransientError,
    PaySwiftUnavailableError,
    PaySwiftValidationError,
)
from .models import (
    PaymentResult,
    PayoutStatus,
    PaySwiftLedgerResponse,
    PaySwiftRequest,
    PaySwiftResponse,
)
from .retry import with_retry

logger = logging.getLogger(__name__)


class PaymentProvider(Protocol):
    def pay_safely(self, request: PaySwiftRequest, idempotency_key: str) -> PaymentResult: ...

    def find_payment_by_reference(
        self, rider_id: str, reference: str, amount: int
    ) -> PaymentResult | None: ...


class PaySwiftClient(PaymentProvider):
    def __init__(self, base_url: str, timeout: float = 3.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _parse_response(self, body: bytes) -> dict[str, Any]:
        try:
            import typing

            return typing.cast(dict[str, Any], json.loads(body.decode("utf-8")))
        except json.JSONDecodeError as e:
            raise PaySwiftProtocolError(f"Malformed provider response: {e}")

    def _execute_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}{path}"
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)

        payload = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status, self._parse_response(response.read())
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                parsed = self._parse_response(body)
            except PaySwiftProtocolError:
                parsed = {"error": body.decode("utf-8", errors="replace")}

            # Raise specific errors based on HTTP status
            if e.code == 400:
                raise PaySwiftValidationError(f"Validation failed: {parsed.get('error')}")
            elif e.code in (401, 403):
                raise PaySwiftAuthenticationError("Authentication failed")
            elif e.code == 404:
                raise PaySwiftNotFoundError("Resource not found")
            elif e.code == 409:
                err = parsed.get("error")
                if err == "idempotency_key_reused":
                    raise PaySwiftConflictError(
                        "Idempotency key reused with different request body"
                    )
                elif err == "request_in_progress":
                    # This is technically transient, maybe we can retry
                    raise PaySwiftTransientError("Request in progress")
                raise PaySwiftConflictError(f"Conflict: {err}")
            elif e.code == 429:
                retry_after = e.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else None
                raise PaySwiftRateLimitError("Rate limited", retry_after=delay)
            elif e.code == 504:
                raise PaySwiftUnavailableError("Gateway timeout (Lost response)")
            elif e.code in (502, 503):
                raise PaySwiftTransientError(f"Service unavailable: {parsed.get('error')}")
            elif e.code >= 500:
                raise PaySwiftTransientError(f"Server error {e.code}")

            raise PaySwiftError(f"Unexpected HTTP {e.code}")
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) or "timed out" in str(e.reason).lower():
                raise PaySwiftTimeoutError("Request timed out")
            raise PaySwiftTransientError(f"Network error: {e.reason}")
        except TimeoutError:
            raise PaySwiftTimeoutError("Request timed out")
        except Exception as e:  # noqa: BLE001
            # Catch RemoteDisconnected and ConnectionResetError
            if "Remote end closed connection" in str(e) or "Connection reset" in str(e):
                raise PaySwiftTransientError(f"Connection dropped: {e}")
            raise PaySwiftError(f"Unexpected error: {e}")

    def create_payment(self, request: PaySwiftRequest, idempotency_key: str) -> PaySwiftResponse:
        _, data = self._execute_request(
            "POST",
            "/v1/payouts",
            data={
                "rider_id": request.rider_id,
                "amount": request.amount,
                "reference": request.reference,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return PaySwiftResponse(
            payout_id=data["payout_id"],
            rider_id=data["rider_id"],
            amount=data["amount"],
            reference=data["reference"],
            status=data["status"],
            created_at=data["created_at"],
        )

    def get_ledger(self, rider_id: str) -> PaySwiftLedgerResponse:
        _, data = self._execute_request("GET", f"/v1/payouts?rider_id={rider_id}")
        payouts = [
            PaySwiftResponse(
                payout_id=item["payout_id"],
                rider_id=item["rider_id"],
                amount=item["amount"],
                reference=item["reference"],
                status=item["status"],
                created_at=item["created_at"],
            )
            for item in data.get("data", [])
        ]
        return PaySwiftLedgerResponse(data=payouts, count=data.get("count", 0))

    def find_payment_by_reference(
        self, rider_id: str, reference: str, amount: int
    ) -> PaymentResult | None:
        """Helper to find an exact matching payment in the ledger."""
        ledger = self.get_ledger(rider_id)
        for p in ledger.data:
            if p.reference == reference and p.amount == amount:
                return PaymentResult(
                    payout_id=p.payout_id,
                    status=PayoutStatus(p.status),
                    rider_id=p.rider_id,
                    amount=p.amount,
                    reference=p.reference,
                )
        return None

    def pay_safely(self, request: PaySwiftRequest, idempotency_key: str) -> PaymentResult:
        """
        Executes a payment request with safety against timeouts and transient failures.
        If a timeout occurs, it checks the ledger before retrying.
        """

        def _is_retryable(e: Exception) -> bool:
            return isinstance(e, PaySwiftTransientError)

        attempts = 0
        max_attempts = 8
        base_delay = 1.0
        last_error: PaySwiftTransientError | None = None

        while attempts < max_attempts:
            attempts += 1
            try:
                # Wrap the exact HTTP call in a tight with_retry loop for transient 500s.
                # However, since a timeout leaves us in an uncertain state, we must catch it
                # here at the top level and check the ledger.
                resp = self.create_payment(request, idempotency_key)
                return PaymentResult(
                    payout_id=resp.payout_id,
                    status=PayoutStatus(resp.status),
                    rider_id=resp.rider_id,
                    amount=resp.amount,
                    reference=resp.reference,
                )
            except PaySwiftTimeoutError:
                logger.warning(
                    f"Timeout submitting payment for rider {request.rider_id} (key: {idempotency_key}). "
                    f"Checking ledger..."
                )
                uncertain = True
                last_error = None
            except PaySwiftRateLimitError as e:
                logger.warning(
                    f"Rate limited submitting payment for rider {request.rider_id} (key: {idempotency_key})."
                )
                uncertain = False
                last_error = e
            except PaySwiftTransientError as e:
                logger.warning(
                    f"Transient error submitting payment for rider {request.rider_id} (key: {idempotency_key}): {e}. "
                    f"Checking ledger to be safe..."
                )
                uncertain = True
                last_error = e

            if uncertain:
                # We are in an uncertain state. We must check the ledger.
                # If the ledger check also transiently fails, we should retry the ledger check!
                try:
                    # We use with_retry just for the ledger check
                    existing = with_retry(
                        max_attempts=3,
                        base_delay=1.0,
                        action=lambda: self.find_payment_by_reference(
                            request.rider_id, request.reference, request.amount
                        ),
                        is_retryable=_is_retryable,
                    )
                    if existing:
                        logger.info(
                            f"Payment already processed and found in ledger for rider {request.rider_id}."
                        )
                        return PaymentResult(
                            payout_id=existing.payout_id,
                            status=PayoutStatus(existing.status),
                            rider_id=existing.rider_id,
                            amount=existing.amount,
                            reference=existing.reference,
                        )
                    else:
                        logger.info("Payment not found in ledger. Safe to retry.")
                except Exception as e:  # noqa: BLE001
                    # If we couldn't even check the ledger, we should probably fail instead of blinding retrying,
                    # or just loop and try again later if we still have attempts.
                    logger.error(f"Failed to check ledger during recovery: {e}")

            if attempts >= max_attempts:
                raise PaySwiftError("Max retries exceeded while in uncertain state.")

            import time

            delay = getattr(last_error, "retry_after", None)
            if delay is None:
                delay = base_delay * (2 ** (attempts - 1))
            time.sleep(delay)

        raise PaySwiftError("Unreachable")
