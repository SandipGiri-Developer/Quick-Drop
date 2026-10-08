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
            
            all_discrepancies = engine.find_discrepancies(rider_id, as_of=as_of)
            total_csv = sum(d.claimable for d in all_discrepancies if d.claimable > 0)
            
            try:
                ledger = payswift.get_ledger(rider_id)
                total_paid = sum(p.amount for p in ledger.data if p.status.lower() == "processed")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Could not fetch ledger for check_discrepancies: {e}")
                total_paid = 0
                
            true_outstanding = max(0, total_csv - total_paid)

            if not discrepancies:
                return f"No discrepancies found for this request. True Outstanding Balance: ₹{true_outstanding}"

            lines = []
            for d in discrepancies:
                lines.append(
                    f"- Date: {d.day}, Trip: {d.trip_id or 'N/A'}, Issue: {d.kind.value}, "
                    f"Owed: ₹{d.owed}, Paid: ₹{d.paid}, Claimable: ₹{d.claimable}"
                )
            lines.append("\n---")
            lines.append(f"Total CSV Discrepancies: ₹{total_csv}")
            lines.append(f"Already Compensated via PaySwift: ₹{total_paid}")
            lines.append(f"True Outstanding Balance: ₹{true_outstanding}")
            return "Found the following discrepancies:\n" + "\n".join(lines)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error checking discrepancies: {e}")
            return f"Error checking discrepancies: {e!s}"

    @tool
    def execute_dispute_resolution(trip_id: str | None = None) -> str:
        """
        Executes the resolution for a verified dispute.
        MUST only be called AFTER checking discrepancies.
        This tool processes discrepancies for the rider.
        Args:
            trip_id: The specific trip ID to resolve. Optional for incentives or daily discrepancies without a specific trip.
        Returns:
            The outcome of the decision engine and execution status.
        """
        try:
            # 1. Recalculate owed amount securely for this specific trip
            from app.domain.timeutil import parse_utc

            as_of = parse_utc("2026-09-23T06:30:00Z")
            discrepancies = engine.find_discrepancies(rider_id, as_of=as_of, trip_id=trip_id)
            
            all_discrepancies = engine.find_discrepancies(rider_id, as_of=as_of)
            total_rider_owed_csv = sum(d.claimable for d in all_discrepancies if d.claimable > 0)

            import datetime

            today_str = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
            auto_payments_today = 0
            total_paid_in_payswift = 0
            try:
                ledger = payswift.get_ledger(rider_id)
                for p in ledger.data:
                    if p.status.lower() == "processed":
                        total_paid_in_payswift += p.amount
                        if p.created_at.startswith(today_str) and p.reference.startswith("dispute_"):
                            auto_payments_today += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Could not fetch ledger: {e}")

            true_outstanding_balance = max(0, total_rider_owed_csv - total_paid_in_payswift)

            if true_outstanding_balance <= 0:
                return "Decision: DENY. No true outstanding balance remains (rider already compensated via PaySwift)."

            csv_trip_owed = sum(d.claimable for d in discrepancies if d.claimable > 0)
            if csv_trip_owed <= 0:
                return "Decision: DENY. No claimable amount is owed for this specific request."

            owed_amount = min(csv_trip_owed, true_outstanding_balance)

            payment_ref = f"dispute_{rider_id}_{trip_id}"
            try:
                existing = payswift.find_payment_by_reference(
                    rider_id, payment_ref, amount=owed_amount
                )
                if existing and existing.status.value == "processed":
                    return f"Decision: PAY. Payment of ₹{owed_amount} was successfully sent via PaySwift. Reference: {existing.reference} (Already Processed)"
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Could not check existing payment: {e}")

            # Use true_outstanding_balance for the threshold decision so the ₹200 limit is
            # evaluated against the full true outstanding balance, not just this trip.
            context = DecisionContext(
                authenticated_rider_id=rider_id,
                owed_amount=true_outstanding_balance,
                auto_payments_today=auto_payments_today,
                is_within_window=any(d.within_window for d in discrepancies if d.claimable > 0),
            )
            decision = decide_dispute(context)

            # 4. Act on the decision
            if decision.outcome == "PAY":
                # Pay only the specific trip's claimable amount (capped by true_outstanding_balance)
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
                from app.db.models import OpsItem, OpsItemStatus

                existing_ops = (
                    db.query(OpsItem)
                    .filter_by(
                        rider_id=rider_id,
                        status=OpsItemStatus.PENDING,
                    )
                    .first()
                )
                if not existing_ops:
                    ops_item = OpsItem(
                        rider_id=rider_id,
                        kind=decision.outcome,
                        amount=true_outstanding_balance,
                        reason=decision.reason,
                        trip_id=None,
                    )
                    db.add(ops_item)
                    db.commit()
                return f"Decision: {decision.outcome}. Item sent to Operations for manual review. Reason: {decision.reason}. Amount: ₹{true_outstanding_balance}."
            else:
                return f"Decision: {decision.outcome}. Reason: {decision.reason}. Amount: ₹{owed_amount}."

        except Exception as e:  # noqa: BLE001
            logger.error(f"Error executing resolution: {e}")
            return f"Error executing resolution: {e!s}"

    return [check_discrepancies, execute_dispute_resolution]
