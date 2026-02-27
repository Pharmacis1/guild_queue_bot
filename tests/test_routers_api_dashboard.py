import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from main import app # Assuming main.py exports the FastAPI `app`
from routers.api_dashboard import *

client = TestClient(app)

# ---------------------------------------------------------
# Fixtures & Mocks
# ---------------------------------------------------------

@pytest.fixture
def mock_current_user():
    # Helper to mock get_current_user depending on test needs
    with patch("routers.api_dashboard.get_current_user") as mock_u:
        yield mock_u

@pytest.fixture
def mock_db_time():
    with patch("routers.api_dashboard.get_last_update_time", return_value="2024-01-01 12:00"):
        yield

class MockCursor:
    def __init__(self, fetchall_data):
        self.fetchall_data = fetchall_data
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def fetchall(self):
        return self.fetchall_data

class MockConnection:
    def __init__(self, fetchall_data):
        self.fetchall_data = fetchall_data
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    def execute(self, query, *args):
        return MockCursor(self.fetchall_data)

# ---------------------------------------------------------
# GET /init
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_init_unauthenticated(mock_current_user, mock_db_time):
    mock_current_user.return_value = None
    
    with patch("routers.api_dashboard.get_last_update_time", return_value="2024-01-01 12:00"):
        with patch("aiosqlite.connect", return_value=MockConnection([{"id": 1, "name": "Q1"}])):
            response = client.get("/api/dashboard/init")
            assert response.status_code == 200
            data = response.json()
            assert data["user"] is None
            assert len(data["queue_types"]) == 1

def test_init_authenticated(mock_current_user, mock_db_time):
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.telegram_id = 123
    mock_user.username = "testuser"
    mock_user.avatar_url = "http://test"
    mock_user.is_master = True
    mock_user.is_banned = False
    mock_current_user.return_value = mock_user
    
    with patch("routers.api_dashboard.get_last_update_time", return_value="2024-01-01 12:00"):
        with patch("aiosqlite.connect", return_value=MockConnection([])):
            response = client.get("/api/dashboard/init")
            assert response.status_code == 200
            data = response.json()
            assert data["user"]["username"] == "testuser"
            assert data["user"]["is_master"] is True

# ---------------------------------------------------------
# GET /kh
# ---------------------------------------------------------

def test_get_kh_data_success(mock_current_user):
    mock_current_user.return_value = None
    
    mock_data = {
        "rows": [{
            "role_id": 1, "name": "Test", "class_id": 1, "total_valor": 100, "total_gold": 100,
            "is_mine": False, "is_newcomer": False, "is_afk": False, "join_date": "2024", "join_days_ago": 1,
            "valor_tier": "1", "gold_tier": "1", "s1": 0, "s2": 0, "s3": 0, "s4": 0, "s5": 0, "s6": 0, "s7": 0,
            "adepts": 0, "dances": 0, "afk_dates": None
        }],
        "start_date": "2024", "end_date": "2024"
    }

    with patch("routers.api_dashboard.get_kh_table_data", return_value=mock_data):
        response = client.get("/api/dashboard/kh?classes=1,2")
        assert response.status_code == 200
        assert response.json()["start_date"] == "2024"

def test_get_kh_data_validation_error(mock_current_user):
    mock_current_user.return_value = None
    # Missing required 'rows' fields to force Pydantic validation error
    mock_data = {"rows": [{"role_id": 1}], "start_date": "2024", "end_date": "2024"}
    
    with patch("routers.api_dashboard.get_kh_table_data", return_value=mock_data):
        with pytest.raises(Exception):
            client.get("/api/dashboard/kh")

# ---------------------------------------------------------
# GET /money
# ---------------------------------------------------------

def test_get_money_data(mock_current_user):
    mock_user = MagicMock()
    mock_char = MagicMock()
    mock_char.nickname = "MyChar"
    mock_user.characters = [mock_char]
    mock_current_user.return_value = mock_user
    
    with patch("routers.api_dashboard.get_money_table_data", return_value={"mock": "data"}) as mock_logic:
        response = client.get("/api/dashboard/money?classes=1")
        assert response.status_code == 200
        # Check if group_period defaulted to 'day'
        mock_logic.assert_called_once_with(None, None, [1], None, "day", 1, {"mychar"})

# ---------------------------------------------------------
# GET /history
# ---------------------------------------------------------

def test_get_history_data(mock_current_user):
    mock_current_user.return_value = None
    
    mock_row = {
        "date": "2024", "name": "Test", "class_id": 1, "class_name": "W", "desc": "kill",
        "type": 1, "role_id": 1, "item_name": None, "is_mine": False, "is_afk": False,
        "timestamp": 123456.0, "afk_dates": None
    }
    
    with patch("routers.api_dashboard.get_history_data", return_value=[mock_row]) as mock_logic:
        response = client.get("/api/dashboard/history?classes=1&types=foo,bar")
        assert response.status_code == 200
        assert len(response.json()) == 1
        mock_logic.assert_called_once_with(None, None, [1], ["foo", "bar"], set())

# ---------------------------------------------------------
# GET /profile/{role_id}
# ---------------------------------------------------------

def test_get_profile_found():
    mock_profile = {
        "role_id": 1, "nickname": "Test", "class_id": 1, "in_clan": True, "is_alt": False,
        "afk_history": [], "queues": [], "linked_chars": [], "parties": [], "party": None,
        "afk_start": "2024-01-01", "afk_end": "2024-01-02", "user_id": 1, "telegram_id": 123, "username": "testuser"
    }
    with patch("logic.player_manager.get_player_profile", return_value=mock_profile):
        response = client.get("/api/dashboard/profile/1")
        assert response.status_code == 200
        assert response.json()["afk_start"] == "2024-01-01"

def test_get_profile_not_found():
    with patch("logic.player_manager.get_player_profile", return_value=None):
        response = client.get("/api/dashboard/profile/999")
        assert response.status_code == 404

# ---------------------------------------------------------
# POST /profile/{role_id}
# ---------------------------------------------------------

def test_post_profile_unauthorized(mock_current_user):
    mock_current_user.return_value = None
    response = client.post("/api/dashboard/profile/1", json={"nickname": "New"})
    assert response.status_code == 401

def test_post_profile_forbidden(mock_current_user):
    mock_user = MagicMock()
    mock_user.is_master = False
    mock_user.id = 100
    mock_current_user.return_value = mock_user
    
    # Mock ownership check to fail
    with patch("routers.api_dashboard.session.query") as mock_query:
        mock_query.return_value.filter_by.return_value.first.return_value = None
        response = client.post("/api/dashboard/profile/1", json={})
        assert response.status_code == 403

def test_post_profile_master_success(mock_current_user):
    mock_user = MagicMock()
    mock_user.is_master = True # Can edit anyone
    mock_current_user.return_value = mock_user
    
    with patch("logic.player_manager.update_player_logic", return_value={"status": "updated"}):
        response = client.post("/api/dashboard/profile/1", json={"name": "x"})
        assert response.status_code == 200
        assert response.json()["status"] == "updated"

def test_post_profile_owner_success(mock_current_user):
    mock_user = MagicMock()
    mock_user.is_master = False
    mock_user.id = 100
    mock_current_user.return_value = mock_user
    
    # Mock ownership check to succeed
    with patch("routers.api_dashboard.session.query") as mock_query:
        mock_query.return_value.filter_by.return_value.first.return_value = MagicMock()
        
        with patch("logic.player_manager.update_player_logic", return_value={"status": "ok"}):
            response = client.post("/api/dashboard/profile/1", json={"name": "x"})
            assert response.status_code == 200

def test_post_profile_logic_error(mock_current_user):
    mock_user = MagicMock()
    mock_user.is_master = True
    mock_current_user.return_value = mock_user
    
    with patch("logic.player_manager.update_player_logic", side_effect=ValueError("Bad Nickname")):
        response = client.post("/api/dashboard/profile/1", json={})
        assert response.status_code == 400
        assert "Bad Nickname" in response.text

# ---------------------------------------------------------
# Test helpers correctly returns None when no session
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_get_current_user_helper():
    # Because endpoints mock get_current_user, we should test the actual function once
    # to cover lines 143-146
    from routers.api_dashboard import get_current_user
    
    # Mock a request with an empty session
    mock_request = MagicMock()
    mock_request.session = {}
    
    res = await get_current_user(mock_request)
    assert res is None
