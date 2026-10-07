from unittest.mock import MagicMock

from evals.adversarial import AdversarialRunner
from evals.client import APIClient
from evals.reporter import EvalResult, Reporter
from evals.runner import Evaluator


def test_api_client() -> None:
    client = APIClient("http://fake")
    client.client = MagicMock()
    
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"reply": "test"}
    client.client.post.return_value = mock_resp
    
    res = client.send_message("R1", "M1", "hello", "time")
    assert res == {"reply": "test"}

def test_runner_pass() -> None:
    api = MagicMock()
    payswift = MagicMock()
    
    api.send_message.return_value = {"reply": "Ok"}
    payswift.get_payouts.return_value = [{"amount": 25, "status": "PROCESSED"}]
    api.get_pending_ops.return_value = []
    
    runner = Evaluator(api, payswift)
    case = {
        "scenario": "test",
        "rider_id": "R003",
        "turns": [{"from": "rider", "message_id": "1", "text": "hi", "received_at": "time"}],
        "expected": {"payout": 25, "approval": None}
    }
    
    result = runner.run_case(0, case)
    assert result.passed is True

def test_runner_fail() -> None:
    api = MagicMock()
    payswift = MagicMock()
    
    api.send_message.return_value = {"reply": "Ok"}
    payswift.get_payouts.return_value = [{"amount": 50, "status": "PROCESSED"}] # Wrong amount
    api.get_pending_ops.return_value = []
    
    runner = Evaluator(api, payswift)
    case = {
        "scenario": "test",
        "rider_id": "R003",
        "turns": [{"from": "rider", "message_id": "1", "text": "hi", "received_at": "time"}],
        "expected": {"payout": 25, "approval": None}
    }
    
    result = runner.run_case(0, case)
    assert result.passed is False

def test_duplicate_message() -> None:
    api = MagicMock()
    payswift = MagicMock()
    
    api.send_message.return_value = {"reply": "Identical"}
    payswift.get_payouts.return_value = [{"amount": 25, "status": "PROCESSED"}]
    
    adv = AdversarialRunner(api, payswift)
    res = adv.test_duplicate_message()
    
    assert res.passed is True
    assert api.send_message.call_count == 2

def test_reporter() -> None:
    rep = Reporter()
    rep.add_result(EvalResult("Test", True, "25", "25"))
    rep.add_result(EvalResult("Test2", False, "0", "100", "Err"))
    
    success = rep.print_report()
    assert success is False
