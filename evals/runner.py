import time
import uuid
from typing import Any

from evals.client import APIClient, PaySwiftClientAPI
from evals.reporter import EvalResult


class Evaluator:
    def __init__(self, api_client: APIClient, payswift_client: PaySwiftClientAPI):
        self.api = api_client
        self.payswift = payswift_client

    def generate_uuid(self) -> str:
        return str(uuid.uuid4())

    def run_case(self, i: int, case: dict[str, Any]) -> EvalResult:
        scenario = case["scenario"]
        name = f"Case {i+1:02d} - {scenario[:30]}..."
        rider_id_base = case["rider_id"]
        # We must use exact rider_id because trips.csv data is tied to them
        test_run_id = self.generate_uuid()[:8]
        test_rider_id = rider_id_base

        expected = case["expected"]
        expected_payout = expected.get("payout", 0)
        expected_approval = expected.get("approval", None)
        # Note: some cases use "one_of"

        try:
            replies = []
            for turn in case["turns"]:
                if turn["from"] == "rider":
                    msg_id = f"{turn['message_id']}_{test_run_id}"
                    text = turn["text"].replace(rider_id_base, test_rider_id) # Just in case they mention their ID
                    resp = self.api.send_message(
                        rider_id=test_rider_id,
                        message_id=msg_id,
                        text=text,
                        received_at=turn["received_at"]
                    )
                    replies.append(resp.get("reply", ""))

            # Wait briefly for ops or payments to propagate
            time.sleep(0.5)

            # Check payouts in PaySwift
            payouts = self.payswift.get_payouts(test_rider_id)
            total_paid = sum(p["amount"] for p in payouts if p["status"].upper() == "PROCESSED")

            # Check pending ops
            ops_items = self.api.get_pending_ops()
            rider_ops = [op for op in ops_items if op["rider_id"] == test_rider_id]
            total_pending = sum(op["amount"] for op in rider_ops)

            # Check logic
            passed = False
            obs_str = f"Payout: {total_paid}, Pending: {total_pending}"
            exp_str = f"Payout: {expected_payout}, Pending: {expected_approval}"

            if "one_of" in expected:
                for opt in expected["one_of"]:
                    exp_p = opt.get("payout", 0)
                    exp_a = opt.get("approval", None)
                    if total_paid == exp_p and ((exp_a is None and total_pending == 0) or (total_pending == exp_a)):
                        passed = True
                        exp_str = "One of Options Matched"
                        break
            else:
                if total_paid == expected_payout:
                    if expected_approval is None:
                        passed = total_pending == 0
                    else:
                        passed = total_pending == expected_approval

            return EvalResult(
                name=name,
                passed=passed,
                expected=exp_str,
                observed=obs_str,
                error="" if passed else "State did not match expected outcomes."
            )

        except Exception as e:  # noqa: BLE001
            return EvalResult(
                name=name,
                passed=False,
                expected="Successful execution",
                observed="Exception raised",
                error=str(e)
            )
