import tempfile
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.main import app
from app.db.models import Base, MessageRecord
from app.db.session import get_db

# Use a temporary file-based SQLite database to avoid threading issues with :memory:
temp_db_file = tempfile.NamedTemporaryFile(delete=False)  # noqa: SIM115
SQLALCHEMY_DATABASE_URL = f"sqlite:///{temp_db_file.name}?timeout=15"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def mock_agent() -> Generator[None, None, None]:
    with patch(
        "app.services.message_service.run_agent",
        return_value="Your message has been received and is being processed.",
    ):
        yield


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


def test_post_message_success() -> None:
    payload = {
        "message_id": "msg_1",
        "rider_id": "R001",
        "text": "Where is my surge?",
        "received_at": "2026-10-06T10:00:00Z",
    }
    response = client.post("/messages", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Your message has been received and is being processed."

    # Check DB
    db = TestingSessionLocal()
    records = db.query(MessageRecord).all()
    assert len(records) == 1
    assert records[0].message_id == "msg_1"
    assert records[0].rider_id == "R001"
    db.close()


def test_post_message_idempotent() -> None:
    payload = {
        "message_id": "msg_idem",
        "rider_id": "R002",
        "text": "Hello",
        "received_at": "2026-10-06T10:00:00Z",
    }
    # First call
    response1 = client.post("/messages", json=payload)
    assert response1.status_code == 200

    # Second call (duplicate)
    response2 = client.post("/messages", json=payload)
    assert response2.status_code == 200
    assert response2.json()["reply"] == response1.json()["reply"]

    # Check DB
    db = TestingSessionLocal()
    records = db.query(MessageRecord).all()
    assert len(records) == 1  # Only one record!
    db.close()


def test_post_message_concurrent_idempotency() -> None:
    payload = {
        "message_id": "msg_concurrent",
        "rider_id": "R003",
        "text": "Concurrent",
        "received_at": "2026-10-06T10:00:00Z",
    }

    def make_request() -> int:
        return int(client.post("/messages", json=payload).status_code)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request) for _ in range(5)]
        results = [f.result() for f in futures]

    assert all(r == 200 for r in results)

    db = TestingSessionLocal()
    records = db.query(MessageRecord).all()
    assert len(records) == 1  # Only one record despite concurrent requests
    db.close()


def test_post_message_validation_error() -> None:
    payload = {
        "message_id": "msg_invalid",
        "rider_id": "invalid_format",  # Should be R000 format
        "text": "Test",
        "received_at": "2026-10-06T10:00:00Z",
    }
    response = client.post("/messages", json=payload)
    assert response.status_code == 422
    assert "rider_id" in response.text
