import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.api.main import app, get_db

client = TestClient(app)

def test_health_success():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}

@patch("app.api.main.get_db")
def test_health_failure(mock_get_db):
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("DB Down")
    
    app.dependency_overrides[get_db] = lambda: mock_db
    
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "Service unavailable"
    
    app.dependency_overrides.clear()

@patch("app.api.main.process_message")
def test_handle_message_exception(mock_process):
    mock_process.side_effect = Exception("Unknown Error")
    
    payload = {
        "message_id": "m1",
        "rider_id": "R123",
        "text": "hello",
        "received_at": "2026-01-01T00:00:00Z"
    }
    response = client.post("/messages", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
