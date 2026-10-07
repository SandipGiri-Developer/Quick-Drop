import time
import uuid

from evals.client import APIClient, PaySwiftClientAPI
from evals.reporter import EvalResult


class AdversarialRunner:
    def __init__(self, api_client: APIClient, payswift_client: PaySwiftClientAPI):
        self.api = api_client
        self.payswift = payswift_client

    def generate_uuid(self) -> str:
        return str(uuid.uuid4())

    def test_duplicate_message(self) -> EvalResult:
        rider_id = "R003"
        msg_id = f"dup_{self.generate_uuid()[:8]}"
        text = "Bhai order T926334 ka surge nahi mila, 20 tarikh wala."

        try:
            # Send message 1
            resp1 = self.api.send_message(rider_id, msg_id, text, "2026-09-22T09:05:00+05:30")
            
            # Send message 2 (duplicate ID)
            resp2 = self.api.send_message(rider_id, msg_id, text, "2026-09-22T09:05:00+05:30")
            
            time.sleep(1)
            payouts = self.payswift.get_payouts(rider_id)
            total = sum(p["amount"] for p in payouts if p["status"] == "PROCESSED")

            passed = (total == 25) and (resp1.get("reply") == resp2.get("reply"))
            return EvalResult(
                name="Adversarial - Duplicate message",
                passed=passed,
                expected="Payout = 25, Idempotent replies",
                observed=f"Payout = {total}",
            )
        except Exception as e:  # noqa: BLE001
            return EvalResult("Adversarial - Duplicate message", False, "", "", str(e))

    def test_payswift_outage(self) -> EvalResult:
        rider_id = "R031"
        msg_id = f"outage_{self.generate_uuid()[:8]}"
        text = "T312538 ka surge nahi mila" # R031 is owed 22

        try:
            # Turn on Chaos
            self.payswift.trigger_chaos(True)
            
            self.api.send_message(rider_id, msg_id, text, "2026-09-23T10:00:00+05:30")
            
            # Turn off chaos so we can inspect
            self.payswift.trigger_chaos(False)
            time.sleep(1)

            # Check payout
            payouts = self.payswift.get_payouts(rider_id)
            total = sum(p["amount"] for p in payouts if p["status"] == "PROCESSED")

            # Check if it was escalated/pending or if the agent reported failure
            # If it failed to pay, it should ideally NOT say it paid successfully.
            # And it should not have paid on PaySwift.
            passed = total == 0
            
            return EvalResult(
                name="Adversarial - PaySwift outage",
                passed=passed,
                expected="Payout = 0 during outage",
                observed=f"Payout = {total}",
            )
        except Exception as e:  # noqa: BLE001
            self.payswift.trigger_chaos(False)
            return EvalResult("Adversarial - PaySwift outage", False, "", "", str(e))

    def test_story_change(self) -> EvalResult:
        rider_id = "R007"
        try:
            # First claim an issue with a trip that is valid
            self.api.send_message(rider_id, "s1", "order T840677 ka surge missing hai", "2026-09-23T09:45:00+05:30")
            
            # Then completely change the story to an invalid trip before confirming
            self.api.send_message(rider_id, "s2", "Wait nahi, T840677 theek hai. Mujhe T999999 ka 500 chahiye", "2026-09-23T09:46:00+05:30")
            
            time.sleep(1)
            payouts = self.payswift.get_payouts(rider_id)
            total = sum(p["amount"] for p in payouts if p["status"] == "PROCESSED")

            passed = total == 0
            return EvalResult(
                name="Adversarial - Story change",
                passed=passed,
                expected="Payout = 0 (Invalid trip)",
                observed=f"Payout = {total}",
            )
        except Exception as e:  # noqa: BLE001
            return EvalResult("Adversarial - Story change", False, "", "", str(e))
