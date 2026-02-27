import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class MockCursor:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
        
    def __await__(self):
        async def _r(): return self
        return _r().__await__()
        
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): pass
        
    async def fetchall(self):
        return self.fetchall_data or []
        
    async def fetchone(self):
        return self.fetchone_data

class MockConnection:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
        
    def __await__(self):
        async def _r(): return self
        return _r().__await__()
        
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): pass
        
    def execute(self, query, *args):
        return MockCursor(self.fetchall_data, self.fetchone_data)

@pytest.fixture
def mock_dependencies():
    with patch("aiosqlite.connect", return_value=MockConnection(fetchall_data=[])) as mock_db, \
         patch("routers.views.get_data_from_db", new_callable=AsyncMock) as mock_get_data, \
         patch("routers.views.get_last_update_time", new_callable=AsyncMock) as mock_upd:
        
        mock_get_data.return_value = (
            [
                {"role_id": 1, "name": "Hero", "class_id": 1, "total_valor": 100, "total_gold": 50, "interval_stats": [{"start": None, "end": None}]}
            ], 
            "2023-01-01", 
            "2023-01-07", 
            []
        )
        mock_upd.return_value = "2023-01-01 12:00:00"
        
        # We also need a mock database session for the local `from database import session`
        # Because it happens inside the function, we patch the source module
        mock_session = MagicMock()
        mock_session.query().filter_by().first.return_value = None
        
        with patch("database.session", mock_session):
            yield mock_db, mock_get_data, mock_session

@pytest.mark.asyncio
async def test_read_root_guest(mock_dependencies):
    from routers.views import read_root
    req = MagicMock()
    req.session = {}
    response = await read_root(req)
    assert hasattr(response, "body")
    assert b"<!DOCTYPE html>" in response.body or b"<html" in response.body

@pytest.mark.asyncio
async def test_read_root_with_params(mock_dependencies):
    from routers.views import read_root
    req = MagicMock()
    req.session = {}
    response = await read_root(
        req,
        kh_start="2023-01-01", kh_end="2023-01-07", kh_classes=[1], kh_newcomers="only",
        money_start="2023-01-01", money_end="2023-01-07", money_group_period="day",
        history_start="2023-01-01", history_types=["valor"]
    )
    assert hasattr(response, "body")

@pytest.mark.asyncio
async def test_read_root_authenticated(mock_dependencies):
    mock_db, _, mock_session = mock_dependencies

    mock_user = MagicMock()
    mock_user.telegram_id = 123
    mock_user.username = "TestUser"
    mock_user.avatar_url = "http://avatar"
    mock_user.is_master = True
    
    mock_char = MagicMock()
    mock_char.nickname = "TestChar"
    mock_char.is_main = True
    mock_user.characters = [mock_char]

    mock_session.query().filter_by().first.return_value = mock_user

    from routers.views import read_root
    req = MagicMock()
    req.session = {"user_id": 123}
    
    response = await read_root(req)
    assert hasattr(response, "body")

def test_admin_auth_page_guest():
    response = client.get("/admin/auth")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_admin_auth_page_admin():
    mock_user = MagicMock()
    mock_user.is_master = True
    
    mock_session = MagicMock()
    mock_session.query().filter_by().first.return_value = mock_user
    
    with patch("starlette.requests.Request.session", {"user_id": 123}), \
         patch("database.session", mock_session):
        response = client.get("/admin/auth")
        assert response.status_code == 200
