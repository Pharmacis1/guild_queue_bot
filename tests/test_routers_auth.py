import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from main import app
from routers.auth import *

client = TestClient(app)

# ---------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------

class MockCursor:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
    
    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc, tb):
        pass
        
    async def fetchall(self):
        return self.fetchall_data
        
    async def fetchone(self):
        return self.fetchone_data

class MockConnection:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
        
    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc, tb):
        pass
        
    def execute(self, query, *args):
        return MockCursor(self.fetchall_data, self.fetchone_data)
        
    async def commit(self):
        pass

# ---------------------------------------------------------
# GET /login/telegram
# ---------------------------------------------------------

def test_login_telegram_no_bot_token():
    with patch("routers.auth.BOT_TOKEN", None):
        response = client.get("/login/telegram?id=123")
        assert response.status_code == 200
        assert "Server Config Error" in response.text

def test_login_telegram_invalid_hash():
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth", side_effect=ValueError("Invalid hash")):
            response = client.get("/login/telegram?id=123&hash=bad")
            assert response.url.path == "/"
            query = response.url.query.decode() if isinstance(response.url.query, bytes) else response.url.query
            assert "error=auth_failed" in query

def test_login_telegram_user_not_found():
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=None)):
                response = client.get("/login/telegram?id=123&photo_url=http")
                assert response.url.path == "/"
                query = response.url.query.decode() if isinstance(response.url.query, bytes) else response.url.query
                assert "error=not_registered" in query

def test_login_telegram_success():
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
                response = client.get("/login/telegram?id=123&photo_url=http")
                assert response.url.path == "/"
                query = response.url.query.decode() if isinstance(response.url.query, bytes) else response.url.query
                assert "error" not in query

# ---------------------------------------------------------
# POST /api/login
# ---------------------------------------------------------

def test_api_login_no_bot_token():
    with patch("routers.auth.BOT_TOKEN", None):
        response = client.post("/api/login", json={"initData": "foo"})
        assert response.status_code == 500
        assert "Config Error" in response.json()["message"]

def test_api_login_invalid_init_data():
    with patch("routers.auth.validate_init_data", side_effect=ValueError("Bad initData")):
        response = client.post("/api/login", json={"initData": "foo"})
        assert response.status_code == 403
        assert "Auth failed" in response.json()["message"]

def test_api_login_no_user_data():
    with patch("routers.auth.validate_init_data", return_value={"other": "data"}):
        response = client.post("/api/login", json={"initData": "foo"})
        assert response.status_code == 400

def test_api_login_user_not_found():
    parsed_data = {"user": {"id": 123}}
    with patch("routers.auth.validate_init_data", return_value=parsed_data):
        with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=None)):
            response = client.post("/api/login", json={"initData": "foo"})
            assert response.status_code == 403
            assert "не зарегистрированы" in response.json()["message"]

def test_api_login_zero_chars():
    parsed_data = {"user": {"id": 123}}
    
    # We need cursor.fetchone to return user_row first, then char_count second.
    # We can mock cursor manually.
    class SequentialCursor:
        def __init__(self, response):
            self.response = response
            
        def __await__(self):
            async def _ret():
                return self
            return _ret().__await__()
            
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def fetchone(self):
            return self.response
            
    class SequentialConnection:
        def __init__(self, cursor_responses):
            self.cursor_responses = cursor_responses
            self.idx = 0

        def __await__(self):
            async def _ret():
                return self
            return _ret().__await__()
            
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        def execute(self, query, *args):
            res = self.cursor_responses[self.idx]
            self.idx += 1
            return SequentialCursor(res)

    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_init_data", return_value=parsed_data):
            # First execute gets User row = (1,), Second gets Char count = (0,)
            with patch("aiosqlite.connect", return_value=SequentialConnection([(1,), (0,)])):
                response = client.post("/api/login", json={"initData": "foo"})
                assert response.status_code == 403
                assert "нет персонажей" in response.json()["message"]

def test_api_login_success():
    parsed_data = {"user": {"id": 123}}
    
    class SequentialCursor:
        def __init__(self, response):
            self.response = response
            
        def __await__(self):
            async def _ret():
                return self
            return _ret().__await__()
            
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def fetchone(self):
            return self.response
            
    class SequentialConnection:
        def __init__(self, cursor_responses):
            self.cursor_responses = cursor_responses
            self.idx = 0

        def __await__(self):
            async def _ret():
                return self
            return _ret().__await__()
            
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        def execute(self, query, *args):
            res = self.cursor_responses[self.idx]
            if self.idx < len(self.cursor_responses) - 1:
                self.idx += 1
            return SequentialCursor(res)
        async def commit(self):
            pass

    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_init_data", return_value=parsed_data):
            with patch("aiosqlite.connect", return_value=SequentialConnection([(1,), (5,)])):
                with patch("routers.auth.get_telegram_avatar_url", new_callable=AsyncMock) as mock_ava:
                    mock_ava.return_value = "http://avatar"
                    response = client.post("/api/login", json={"initData": "foo"})
                    assert response.status_code == 200
                    assert response.json()["message"] == "Logged in"

def test_api_login_exception():
    with patch("routers.auth.validate_init_data", side_effect=Exception("DB Crash")):
        response = client.post("/api/login", json={"initData": "foo"})
        assert response.status_code == 500

# ---------------------------------------------------------
# POST /api/login/widget
# ---------------------------------------------------------

def test_widget_login_no_bot_token():
    with patch("routers.auth.BOT_TOKEN", None):
        response = client.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
        assert response.status_code == 500

def test_widget_login_invalid_hash():
    with patch("routers.auth.validate_widget_auth", side_effect=ValueError("Bad hash")):
        response = client.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
        assert response.status_code == 403

def test_widget_login_user_not_found():
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=None)):
                response = client.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
                assert response.status_code == 403
                assert "не зарегистрированы" in response.json()["message"]

def test_widget_login_success():
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
                with patch("routers.auth.get_telegram_avatar_url", new_callable=AsyncMock) as mock_ava:
                    mock_ava.return_value = "http://avatar"
                    
                    # Test with no photo_url to trigger get_telegram_avatar_url fallback
                    payload = {"id": 123, "first_name": "a", "auth_date": 1, "hash": "a"}
                    response = client.post("/api/login/widget", json=payload)
                    assert response.status_code == 200
                    assert mock_ava.call_count == 1

def test_widget_login_exception():
    with patch("routers.auth.validate_widget_auth", side_effect=Exception("DB Crash")):
        response = client.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
        assert response.status_code == 500

# ---------------------------------------------------------
# GET, POST /logout
# ---------------------------------------------------------

def test_logout_post():
    response = client.post("/api/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out"

def test_logout_get():
    # Will redirect
    response = client.get("/logout", allow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/"
