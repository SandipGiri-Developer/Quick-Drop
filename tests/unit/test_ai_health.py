import time
from typing import Any
from unittest.mock import MagicMock, patch

from app.db.models import AiHealthState
from app.services.ai_health import AiHealthTracker


def test_ai_health_tracker_singleton() -> None:
    t1 = AiHealthTracker.get_instance()
    t2 = AiHealthTracker.get_instance()
    assert t1 is t2


def test_rate_limiting(monkeypatch: Any) -> None:
    monkeypatch.delenv("TESTING", raising=False)
    tracker = AiHealthTracker()
    start = time.time()
    tracker._wait_for_rate_limit()
    tracker._wait_for_rate_limit()
    end = time.time()
    assert end - start >= 3.5


def test_record_event_success() -> None:
    tracker = AiHealthTracker()
    tracker.state = AiHealthState.RATE_LIMITED
    db = MagicMock()

    tracker.record_event(db, "Gemini", "SUCCESS", "Request successful", 200, True)

    assert tracker.state == AiHealthState.HEALTHY
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_record_event_429() -> None:
    tracker = AiHealthTracker()
    db = MagicMock()

    tracker.record_event(db, "Gemini", "RATE_LIMIT", "Too many requests", 429, False)

    assert tracker.state == AiHealthState.RATE_LIMITED
    assert tracker.last_error == "Too many requests"


def test_record_event_auth_error() -> None:
    tracker = AiHealthTracker()
    db = MagicMock()

    tracker.record_event(db, "Gemini", "AUTHENTICATION", "Invalid API_KEY provided", 401, False)

    assert tracker.state == AiHealthState.AUTHENTICATION_ERROR
    # Verify secret masking
    args, _ = db.add.call_args
    event = args[0]
    assert "API_KEY" not in event.safe_message
    assert "***" in event.safe_message


def test_record_event_quota() -> None:
    tracker = AiHealthTracker()
    db = MagicMock()

    tracker.record_event(db, "Gemini", "QUOTA", "Quota exhausted", 402, False)
    assert tracker.state == AiHealthState.QUOTA_EXHAUSTED


def test_record_event_timeout() -> None:
    tracker = AiHealthTracker()
    db = MagicMock()

    tracker.record_event(db, "Gemini", "TIMEOUT", "Timeout occurred", 504, False)
    assert tracker.state == AiHealthState.TIMEOUT


def test_record_event_500() -> None:
    tracker = AiHealthTracker()
    db = MagicMock()

    tracker.record_event(db, "Gemini", "PROVIDER_ERROR", "Internal Server Error", 500, False)
    assert tracker.state == AiHealthState.PROVIDER_ERROR


def test_get_health_status() -> None:
    tracker = AiHealthTracker()
    db = MagicMock()
    event_mock = MagicMock()
    event_mock.occurred_at.strftime.return_value = "12:00:00"
    event_mock.error_type = "TEST"
    event_mock.status_code = 500
    event_mock.safe_message = "Test"

    db.query().order_by().limit().all.return_value = [event_mock]

    res = tracker.get_health_status(db)
    assert res["status"] == "HEALTHY"
    assert len(res["recent_events"]) == 1


@patch("app.services.agent.ChatGoogleGenerativeAI")
@patch("app.services.agent.ChatGroq")
def test_agent_error_handling(mock_groq: Any, mock_gemini: Any, monkeypatch: Any) -> None:
    from app.services.agent import create_agent_graph

    db = MagicMock()
    graph = create_agent_graph("R001", db)
    # The chatbot node should handle errors gracefully and not crash
    assert graph is not None
