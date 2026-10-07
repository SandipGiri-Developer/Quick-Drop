from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.main import app
from app.db.models import OpsItem, OpsItemStatus
from app.infrastructure.payswift.models import PaymentResult, PayoutStatus

client = TestClient(app)

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db

# Use SQLite in-memory for fast API tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Override get_db
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.clear()


def test_trace_creation(db_session: Session) -> None:
    from app.services.trace_service import TraceService

    TraceService.add_trace(db_session, "R001", "USER_MESSAGE", "Hello")

    response = client.get("/trace/R001")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["action_type"] == "USER_MESSAGE"


def test_trace_not_found(db_session: Session) -> None:
    response = client.get("/trace/UNKNOWN")
    assert response.status_code == 200
    assert response.json() == []


def test_ops_pending(db_session: Session) -> None:
    item = OpsItem(rider_id="R002", kind="APPROVAL_REQUIRED", amount=150, reason="Needs review")
    db_session.add(item)
    db_session.commit()

    response = client.get("/ops/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(i["rider_id"] == "R002" for i in data)


@patch("app.infrastructure.payswift.client.PaySwiftClient.pay_safely")
def test_ops_approve(mock_pay: MagicMock, db_session: Session) -> None:
    mock_pay.return_value = PaymentResult(
        payout_id="pay_123",
        status=PayoutStatus.PROCESSED,
        rider_id="R002",
        reference="ref_123",
        amount=150,
    )
    item = OpsItem(rider_id="R002", kind="APPROVAL_REQUIRED", amount=150, reason="Needs review")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    response = client.post(f"/ops/pending/{item.id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    db_session.refresh(item)
    assert item.status == OpsItemStatus.APPROVED

    # Check trace
    traces = client.get("/trace/R002").json()
    assert any(t["action_type"] == "OPS_APPROVED" for t in traces)


def test_ops_reject(db_session: Session) -> None:
    item = OpsItem(rider_id="R003", kind="ESCALATE", amount=0, reason="Sus")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    response = client.post(f"/ops/pending/{item.id}/reject")
    assert response.status_code == 200

    db_session.refresh(item)
    assert item.status == OpsItemStatus.REJECTED


def test_approve_already_approved(db_session: Session) -> None:
    item = OpsItem(
        rider_id="R004",
        kind="APPROVAL_REQUIRED",
        amount=150,
        reason="Needs review",
        status=OpsItemStatus.APPROVED,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    response = client.post(f"/ops/pending/{item.id}/approve")
    assert response.status_code == 400
    assert "no longer actionable" in response.json()["detail"]


# Property testing: one actionable approval -> exactly one payout (in mock)
import warnings

from hypothesis import HealthCheck
from sqlalchemy.exc import SAWarning


@settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.sampled_from(["approve", "reject"]), min_size=2, max_size=5))
def test_concurrent_idempotency_simulation(db_session: Session, actions: list[str]) -> None:
    # We ignore SAWarning here because Hypothesis reuses the function-scoped db_session 
    # across multiple iterations. When we DELETE all rows, SQLite resets the auto-increment counter. 
    # So the next inserted OpsItem gets id=1 again, conflicting with the previous iteration's object 
    # that is still in the SQLAlchemy identity map. This is harmless test-only artifact.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=SAWarning)
        db_session.expunge_all()
        db_session.execute(text("DELETE FROM traces"))
        db_session.execute(text("DELETE FROM ops_items"))
        item = OpsItem(rider_id="R005", kind="APPROVAL_REQUIRED", amount=100, reason="Idempotency")
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)
    item_id = item.id

    with patch("app.infrastructure.payswift.client.PaySwiftClient.pay_safely") as mock_pay:
        mock_pay.return_value = PaymentResult(
            payout_id="pay_123",
            status=PayoutStatus.PROCESSED,
            rider_id="R005",
            reference="ref",
            amount=100,
        )

        results = []
        for action in actions:
            # We run sequentially here, but DB locks (with_for_update) protect real concurrency
            results.append(client.post(f"/ops/pending/{item_id}/{action}").status_code)

        # Only the first action should succeed (200), others should be 400 (no longer actionable)
        assert results[0] == 200
        assert all(r == 400 for r in results[1:])

        if actions[0] == "approve":
            mock_pay.assert_called_once()
        else:
            mock_pay.assert_not_called()
