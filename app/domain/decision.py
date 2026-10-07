from enum import Enum

from pydantic import BaseModel


class DecisionOutcome(str, Enum):
    PAY = "PAY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class DisputeDecision(BaseModel):
    outcome: DecisionOutcome
    amount: int
    reason: str
    ops_action_required: bool


class DecisionContext(BaseModel):
    authenticated_rider_id: str
    claimed_rider_id: str | None = None
    owed_amount: int
    auto_payments_today: int
    is_within_window: bool
    has_suspicious_data: bool = False
    has_contradictory_data: bool = False
    has_missing_data: bool = False


def decide_dispute(context: DecisionContext) -> DisputeDecision:
    """
    Deterministic decision engine for rider disputes.
    Enforces financial guardrails before any payout execution.
    """
    # 5. Rider identity
    if (
        context.claimed_rider_id
        and context.claimed_rider_id.strip().upper()
        != context.authenticated_rider_id.strip().upper()
    ):
        return DisputeDecision(
            outcome=DecisionOutcome.DENY,
            amount=0,
            reason="Claimed rider ID does not match authenticated rider ID.",
            ops_action_required=False,
        )

    # 6. Unclear or suspicious cases
    if context.has_suspicious_data or context.has_contradictory_data or context.has_missing_data:
        return DisputeDecision(
            outcome=DecisionOutcome.ESCALATE,
            amount=0,
            reason="Dispute contains unclear, missing, or contradictory information.",
            ops_action_required=True,
        )

    # 4. Seven-day claim window
    if not context.is_within_window:
        return DisputeDecision(
            outcome=DecisionOutcome.DENY,
            amount=0,
            reason="Claim is outside the allowed 7-day window.",
            ops_action_required=False,
        )

    # Validate amount formatting/logic bounds (Rule 2)
    if context.owed_amount <= 0:
        return DisputeDecision(
            outcome=DecisionOutcome.DENY,
            amount=0,
            reason="No amount is owed.",
            ops_action_required=False,
        )

    # 3. Once per rider per day
    if context.auto_payments_today > 0:
        return DisputeDecision(
            outcome=DecisionOutcome.APPROVAL_REQUIRED,
            amount=context.owed_amount,
            reason="Rider has already received an automatic payment today.",
            ops_action_required=True,
        )

    # 1. ₹200 automatic-payment limit
    if context.owed_amount <= 200:
        return DisputeDecision(
            outcome=DecisionOutcome.PAY,
            amount=context.owed_amount,
            reason="Valid claim eligible for automatic payment.",
            ops_action_required=False,
        )
    else:
        return DisputeDecision(
            outcome=DecisionOutcome.APPROVAL_REQUIRED,
            amount=context.owed_amount,
            reason="Owed amount exceeds automatic payment limit of ₹200.",
            ops_action_required=True,
        )
