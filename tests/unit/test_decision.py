from hypothesis import given
from hypothesis import strategies as st

from app.domain.decision import (
    DecisionContext,
    DecisionOutcome,
    decide_dispute,
)


def test_valid_automatic_payment_under_200() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=150,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.PAY
    assert decision.amount == 150
    assert not decision.ops_action_required


def test_valid_automatic_payment_exactly_200() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=200,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.PAY
    assert decision.amount == 200
    assert not decision.ops_action_required


def test_amount_over_200_requires_approval() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=201,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.APPROVAL_REQUIRED
    assert decision.amount == 201
    assert decision.ops_action_required


def test_amount_zero_denied() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=0,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.DENY
    assert decision.amount == 0
    assert not decision.ops_action_required


def test_amount_below_zero_denied() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=-50,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.DENY
    assert decision.amount == 0
    assert not decision.ops_action_required


def test_first_payment_of_the_day() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.PAY


def test_second_payment_for_same_rider_requires_approval() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=1,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.APPROVAL_REQUIRED
    assert decision.amount == 100
    assert decision.ops_action_required


def test_different_riders_can_independently_receive_payments() -> None:
    context1 = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
    )
    context2 = DecisionContext(
        authenticated_rider_id="R002",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision1 = decide_dispute(context1)
    decision2 = decide_dispute(context2)
    assert decision1.outcome == DecisionOutcome.PAY
    assert decision2.outcome == DecisionOutcome.PAY


def test_claim_outside_7_day_window_denied() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=False,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.DENY
    assert decision.amount == 0
    assert not decision.ops_action_required


def test_missing_or_invalid_required_data_escalated() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
        has_missing_data=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.ESCALATE
    assert decision.amount == 0
    assert decision.ops_action_required


def test_contradictory_information_escalated() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
        has_contradictory_data=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.ESCALATE
    assert decision.amount == 0
    assert decision.ops_action_required


def test_suspicious_case_escalated() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
        has_suspicious_data=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.ESCALATE
    assert decision.amount == 0
    assert decision.ops_action_required


def test_rider_id_supplied_in_claim_cannot_override() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        claimed_rider_id="R002",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.DENY
    assert decision.amount == 0
    assert decision.reason == "Claimed rider ID does not match authenticated rider ID."


def test_rider_id_supplied_in_claim_matches() -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        claimed_rider_id="r001",
        owed_amount=100,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)
    assert decision.outcome == DecisionOutcome.PAY
    assert decision.amount == 100


# Property-based tests for financial invariants


@given(
    owed_amount=st.integers(min_value=-1000, max_value=1000),
    auto_payments_today=st.integers(min_value=0, max_value=5),
    is_within_window=st.booleans(),
    has_issues=st.booleans(),
)
def test_invariant_payment_amount_never_exceeds_owed_amount(
    owed_amount: int, auto_payments_today: int, is_within_window: bool, has_issues: bool
) -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=owed_amount,
        auto_payments_today=auto_payments_today,
        is_within_window=is_within_window,
        has_suspicious_data=has_issues,
    )
    decision = decide_dispute(context)

    # Invariant 1: amount_paid <= amount_owed
    if owed_amount >= 0:
        assert decision.amount <= owed_amount
    else:
        assert decision.amount == 0


@given(
    owed_amount=st.integers(min_value=0, max_value=1000),
)
def test_invariant_automatic_payment_never_exceeds_200(owed_amount: int) -> None:
    context = DecisionContext(
        authenticated_rider_id="R001",
        owed_amount=owed_amount,
        auto_payments_today=0,
        is_within_window=True,
    )
    decision = decide_dispute(context)

    # Invariant 2: automatic_payment <= 200
    if decision.outcome == DecisionOutcome.PAY:
        assert decision.amount <= 200
        assert decision.amount == owed_amount
    else:
        if owed_amount > 200:
            assert decision.outcome == DecisionOutcome.APPROVAL_REQUIRED
            assert decision.amount == owed_amount
        else:
            assert decision.outcome == DecisionOutcome.DENY
            assert decision.amount == 0
