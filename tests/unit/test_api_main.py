from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.main import app
from app.db.session import get_db

client = TestClient(app)


def test_health_success() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


@patch("app.api.main.get_db")
def test_health_failure(mock_get_db: MagicMock) -> None:
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("DB Down")

    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "Service unavailable"

    app.dependency_overrides.clear()


@patch("app.api.main.process_message")
def test_handle_message_exception(mock_process: MagicMock) -> None:
    mock_process.side_effect = Exception("Unknown Error")

    payload = {
        "message_id": "m1",
        "rider_id": "R123",
        "text": "hello",
        "received_at": "2026-01-01T00:00:00Z",
    }
    response = client.post("/messages", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
