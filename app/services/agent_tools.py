import logging
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.core.config import settings
from app.data.loader import CsvPayoutRepository, CsvTripRepository
from app.domain.decision import DecisionContext, decide_dispute
from app.domain.reconciliation import ReconciliationService
from app.infrastructure.payswift.client import PaySwiftClient

logger = logging.getLogger(__name__)


# We use a dependency injection approach for the tools so they can access the DB and repos.
# LangChain tools can be created dynamically inside a factory function.


def get_agent_tools(db: Session, rider_id: str) -> list[Any]:

    trip_repo = CsvTripRepository()
    payout_repo = CsvPayoutRepository()
    engine = ReconciliationService(trip_repo, payout_repo)
    payswift = PaySwiftClient(str(settings.payswift_base_url))

    @tool
    def check_discrepancies(trip_id: str | None = None) -> str:
        """
        Checks the rider's ledger for any payout discrepancies.
        Use this tool to find out if the rider is owed any money, either for a specific trip or overall.
        Args:
            trip_id: Optional trip ID to check. If omitted, checks all recent trips for the rider.
        Returns:
            A text summary of all found discrepancies and owed amounts.
        """
        try:
            from app.domain.timeutil import parse_utc

            as_of = parse_utc("2026-09-23T06:30:00Z")
            discrepancies = engine.find_discrepancies(rider_id, as_of=as_of, trip_id=trip_id)
            if not discrepancies:
                return "No discrepancies found. The rider has been paid correctly according to the ledger."

            lines = []
            for d in discrepancies:
                lines.append(
                    f"- Date: {d.day}, Trip: {d.trip_id or 'N/A'}, Issue: {d.kind.value}, "
                    f"Owed: ₹{d.owed}, Paid: ₹{d.paid}, Claimable: ₹{d.claimable}"
                )
            return "Found the following discrepancies:\n" + "\n".join(lines)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error checking discrepancies: {e}")
            return f"Error checking discrepancies: {e!s}"

    @tool
    def execute_dispute_resolution(trip_id: str) -> str:
        """
        Executes the resolution for a verified dispute.
        MUST only be called AFTER checking discrepancies.
        This tool processes discrepancies for the rider.
        Args:
            trip_id: The specific trip ID to resolve. REQUIRED.
        Returns:
            The outcome of the decision engine and execution status.
        """
        try:
            # 1. Recalculate owed amount securely for this specific trip
            from app.domain.timeutil import parse_utc

            as_of = parse_utc("2026-09-23T06:30:00Z")
            discrepancies = engine.find_discrepancies(rider_id, as_of=as_of, trip_id=trip_id)
            owed_amount = sum(d.claimable for d in discrepancies if d.claimable > 0)

            if owed_amount <= 0:
                return "Decision: DENY. No claimable amount is owed for this dispute."

            # 1a. CRITICAL: Compute the TOTAL outstanding balance across ALL trips for this rider.
            # The ₹200 auto-pay limit applies to the rider's ENTIRE outstanding balance, not per-trip.
            # If total > ₹200, no individual trip may be auto-paid — the whole batch goes to ops.
            all_discrepancies = engine.find_discrepancies(rider_id, as_of=as_of)
            total_rider_owed = sum(d.claimable for d in all_discrepancies if d.claimable > 0)

            # 2. Check how many automatic payments were made today by querying the ledger.
            import datetime

            today_str = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
            auto_payments_today = 0
            try:
                ledger = payswift.get_ledger(rider_id)
                auto_payments_today = sum(
                    1
                    for p in ledger.data
                    if p.status.lower() == "processed" and p.created_at.startswith(today_str)
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Could not fetch ledger to check auto_payments_today: {e}")

            payment_ref = f"dispute_{rider_id}_{trip_id}"
            try:
                existing = payswift.find_payment_by_reference(
                    rider_id, payment_ref, amount=owed_amount
                )
                if existing and existing.status.value == "processed":
                    return f"Decision: PAY. Payment of ₹{owed_amount} was successfully sent via PaySwift. Reference: {existing.reference} (Already Processed)"
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Could not check existing payment: {e}")

            # Use total_rider_owed for the threshold decision so the ₹200 limit is
            # evaluated against the full outstanding balance, not just this trip.
            context = DecisionContext(
                authenticated_rider_id=rider_id,
                owed_amount=total_rider_owed,
                auto_payments_today=auto_payments_today,
                is_within_window=any(d.within_window for d in discrepancies if d.claimable > 0),
            )
            decision = decide_dispute(context)

            # 4. Act on the decision
            if decision.outcome == "PAY":
                # Pay only the specific trip's claimable amount (total was used for threshold only)
                try:
                    from app.infrastructure.payswift.models import PaySwiftRequest

                    req = PaySwiftRequest(
                        rider_id=rider_id, amount=owed_amount, reference=payment_ref
                    )
                    response = payswift.pay_safely(request=req, idempotency_key=payment_ref)
                    return f"Decision: PAY. Payment of ₹{owed_amount} was successfully sent via PaySwift. Reference: {response.reference}"
                except Exception as e:  # noqa: BLE001
                    return f"Decision: PAY, but execution failed via PaySwift: {e}"
            elif decision.outcome in ("APPROVAL_REQUIRED", "ESCALATE"):
                from app.db.models import OpsItem

                existing_ops = db.query(OpsItem).filter_by(
                    rider_id=rider_id, kind=decision.outcome, amount=owed_amount, trip_id=trip_id
                ).first()
                if not existing_ops:
                    ops_item = OpsItem(
                        rider_id=rider_id,
                        kind=decision.outcome,
                        amount=owed_amount,
                        reason=decision.reason,
                        trip_id=trip_id,
                    )
                    db.add(ops_item)
                    db.commit()
                return f"Decision: {decision.outcome}. Item sent to Operations for manual review. Reason: {decision.reason}. Amount: ₹{owed_amount}."
            else:
                return f"Decision: {decision.outcome}. Reason: {decision.reason}. Amount: ₹{owed_amount}."

        except Exception as e:  # noqa: BLE001
            logger.error(f"Error executing resolution: {e}")
            return f"Error executing resolution: {e!s}"

    return [check_discrepancies, execute_dispute_resolution]
