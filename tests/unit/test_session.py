import pytest
from unittest.mock import patch, MagicMock
from app.db.session import get_db

def test_get_db():
    mock_session = MagicMock()
    with patch("app.db.session.SessionLocal", return_value=mock_session):
        gen = get_db()
        db = next(gen)
        assert db is mock_session
        
        with pytest.raises(StopIteration):
            next(gen)
            
        mock_session.close.assert_called_once()
