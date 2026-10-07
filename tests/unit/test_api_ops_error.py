from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

from app.api.ops import get_db


@patch("app.api.ops.get_db")
def test_ops_endpoints_exceptions(mock_get_db):
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception("DB Down")

    app.dependency_overrides[get_db] = lambda: mock_db

    # We will test routes that have except blocks:
    # /ops/pending/{item_id}/approve
    # /ops/pending/{item_id}/reject
    # /ops/ai-health

    # We need an item in the DB so it hits the try block
    # Actually wait, `approve` and `reject` have `.first()` before the try block!
    # If the mock_db raises an Exception on `.first()`, they might fail at 500 but on the wrong line.
    # To hit the EXCEPT block in `approve` and `reject`, we must mock `.first()` to return an item.
