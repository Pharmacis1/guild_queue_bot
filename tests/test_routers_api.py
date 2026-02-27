import pytest
import os
import io
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from main import app
from web_database import DB_NAME

client = TestClient(app)

class MockCursor:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
        self.execute_queries = []
        
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
        self.execute_queries = []
        
    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc, tb):
        pass
        
    def execute(self, query, *args):
        self.execute_queries.append((query, args))
        return MockCursor(self.fetchall_data, self.fetchone_data)
        
    async def commit(self):
        pass

# -------------------------------------------------------------
# File operations
# -------------------------------------------------------------
def test_download_watcher_missing():
    with patch("os.path.exists", return_value=False):
        response = client.get("/api/download/watcher")
        assert response.status_code == 404

def test_download_watcher_exists():
    with patch("os.path.exists", return_value=True):
        with patch("fastapi.responses.FileResponse.__init__", return_value=None), \
             patch("fastapi.responses.FileResponse.__call__", new_callable=AsyncMock):
            # Mocking FileResponse entirely might be tricky with TestClient,
            # Let's mock os.stat and open instead, or let TestClient handle a dummy file
            pass

    # Actually simpler: create a dummy file
    dummy_path = "dist/PW_Requiem_history.zip"
    os.makedirs("dist", exist_ok=True)
    with open(dummy_path, "wb") as f:
        f.write(b"dummy")
        
    response = client.get("/api/download/watcher")
    assert response.status_code == 200
    os.remove(dummy_path)

def test_upload_log():
    file_content = b"test log content"
    files = {"file": ("test.log", io.BytesIO(file_content), "text/plain")}
    
    with patch("routers.api.log_importer.process_log_upload", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = ({"status": "ok", "message": "Imported"}, [123], True)
        
        response = client.post("/api/upload", files=files)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_process.assert_called_once()

# -------------------------------------------------------------
# Get Player
# -------------------------------------------------------------
def test_get_player_missing_id():
    response = client.post("/api/get_player", json={})
    assert response.json()["status"] == "error"

def test_get_player_success():
    with patch("routers.api.get_player_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"role_id": 123, "nickname": "TestPlayer"}
        response = client.post("/api/get_player", json={"role_id": 123})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["player"]["nickname"] == "TestPlayer"

def test_get_player_not_found():
    with patch("routers.api.get_player_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        response = client.post("/api/get_player", json={"role_id": 123})
        assert response.json()["status"] == "error"
        assert "not found" in response.json()["message"]

# -------------------------------------------------------------
# AFK endpoints
# -------------------------------------------------------------
def test_afk_add_missing():
    response = client.post("/api/afk/add", json={"start": "2023-01-01"})
    assert response.json()["status"] == "error"

def test_afk_add_success():
    with patch("aiosqlite.connect", return_value=MockConnection()):
        response = client.post("/api/afk/add", json={"role_id": 123, "start": "2023-01-01", "end": "2023-01-02"})
        assert response.json()["status"] == "ok"

def test_afk_delete_missing():
    response = client.post("/api/afk/delete", json={})
    assert response.json()["status"] == "error"

def test_afk_delete_success():
    with patch("aiosqlite.connect", return_value=MockConnection()):
        response = client.post("/api/afk/delete", json={"afk_id": 10})
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Queue endpoints
# -------------------------------------------------------------
def test_queue_join():
    with patch("routers.api.queue_manager.join_queue", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = {"status": "ok"}
        response = client.post("/api/queue/join", json={"user_id": 1, "queue_id": 2, "character_name": "Hero"})
        assert response.json()["status"] == "ok"
        
def test_queue_join_missing():
    response = client.post("/api/queue/join", json={"user_id": 1})
    assert response.json()["status"] == "error"

def test_queue_leave():
    with patch("routers.api.queue_manager.leave_queue", new_callable=AsyncMock) as mock_leave:
        mock_leave.return_value = {"status": "ok"}
        response = client.post("/api/queue/leave", json={"entry_id": 10})
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Character Link/Unlink
# -------------------------------------------------------------
def test_character_link():
    mock_conn = MockConnection(fetchone_data=(1, "Test"))
    with patch("aiosqlite.connect", return_value=mock_conn):
        response = client.post("/api/character/link", json={"user_id": 100, "nickname": "Test"})
        assert response.json()["status"] == "ok"

def test_character_unlink():
    mock_conn = MockConnection(fetchone_data=("TestNick",))
    with patch("aiosqlite.connect", return_value=mock_conn):
        response = client.post("/api/character/unlink", json={"role_id": 123})
        assert response.json()["status"] == "ok"

    with patch("aiosqlite.connect", return_value=mock_conn):
        response = client.post("/api/character/unlink", json={"nickname": "TestNick"})
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Party Endpoints
# -------------------------------------------------------------
def test_party_get():
    with patch("routers.api.party_manager.get_party", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok", "party": {}}
        response = client.post("/api/party/get", json={"role_id": 123})
        assert response.json()["status"] == "ok"

def test_party_add_member_missing_db():
    mock_conn = MockConnection(fetchone_data=None)
    with patch("aiosqlite.connect", return_value=mock_conn):
        response = client.post("/api/party/add_member", json={"party_id": 1, "nickname": "Bob"})
        assert response.json()["status"] == "error"
        assert "не найден" in response.json()["message"]

def test_party_add_member_success():
    class SeqCursor:
        def __init__(self, response):
            self.response = response
        def __await__(self):
            async def _r(): return self
            return _r().__await__()
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        async def fetchone(self):
            return self.response
            
    class SeqConn:
        def __init__(self, cursor_responses):
            self.cursor_responses = cursor_responses
            self.idx = 0
            
        def __await__(self):
            async def _r(): return self
            return _r().__await__()
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        
        def execute(self, query, *args):
            res = self.cursor_responses[self.idx]
            if self.idx < len(self.cursor_responses) - 1:
                self.idx += 1
            return SeqCursor(res)
            
        async def commit(self): pass

    # First fetch: player row (123,). Second fetch: party_members check (None).
    with patch("aiosqlite.connect", return_value=SeqConn([(123,), None, None])):
        response = client.post("/api/party/add_member", json={"party_id": 1, "nickname": "Bob"})
        assert response.json()["status"] == "ok"

def test_party_add():
    with patch("routers.api.party_manager.add_to_party", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/party/add", json={"leader_role_id": 1, "nickname": "Alice"})
        assert response.json()["status"] == "ok"

def test_party_remove():
    with patch("routers.api.party_manager.remove_from_party", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/party/remove", json={"member_role_id": 1})
        assert response.json()["status"] == "ok"

def test_party_rename():
    with patch("routers.api.party_manager.rename_party", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/party/rename", json={"party_id": 1, "name": "Best"})
        assert response.json()["status"] == "ok"

def test_party_color():
    with patch("routers.api.party_manager.update_party_color", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/party/color", json={"party_id": 1, "color": "#FFF"})
        assert response.json()["status"] == "ok"

def test_party_kick():
    with patch("routers.api.party_manager.remove_from_party", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/party/kick", json={"member_role_id": 1})
        assert response.json()["status"] == "ok"

def test_party_transfer():
    with patch("routers.api.party_manager.transfer_leadership", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/party/transfer_leadership", json={"party_id": 1, "new_leader_role_id": 2})
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Player Edits
# -------------------------------------------------------------
def test_update_player():
    with patch("routers.api.update_player_logic", new_callable=AsyncMock) as m:
        m.return_value = {"status": "ok"}
        response = client.post("/api/update_player", json={"role_id": 1})
        assert response.json()["status"] == "ok"

def test_update_nickname():
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
        response = client.post("/api/update_nickname", json={"role_id": 1, "nickname": "NewNick"})
        assert response.json()["status"] == "ok"

def test_update_class():
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
        response = client.post("/api/update_class", json={"role_id": 1, "class_id": 0})
        assert response.json()["status"] == "ok"

def test_update_status():
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
        response = client.post("/api/update_status", json={"role_id": 1, "in_clan": True})
        assert response.json()["status"] == "ok"
        
# -------------------------------------------------------------
# Events
# -------------------------------------------------------------
def test_update_event_date():
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
        response = client.post("/api/update_event_date", json={
            "role_id": 1, "old_timestamp": 1234567, "new_date_str": "2023-10-10 10:10:10"
        })
        assert response.json()["status"] == "ok"

def test_add_event():
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=(1,))):
        response = client.post("/api/add_event", json={
            "role_id": 1, "date": "2023-10-10T10:10:10", "value": 50
        })
        assert response.json()["status"] == "ok"

def test_delete_event():
    with patch("aiosqlite.connect", return_value=MockConnection()):
        response = client.post("/api/delete_event", json={"role_id": 1, "timestamp": 1234567})
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Scraper / Debug
# -------------------------------------------------------------
def test_trigger_scrape():
    # If module is imported
    with patch("routers.api.pwobs_scraper", MagicMock()):
        response = client.post("/api/scrape_players", json={"server": "capella"})
        assert response.json()["status"] == "ok"

def test_get_debug_screenshot():
    with patch("os.path.exists", return_value=True):
        # Create dummy image
        with open("login_failed.png", "wb") as f: f.write(b"dummy")
        response = client.get("/api/debug_screenshot")
        assert response.status_code == 200
        os.remove("login_failed.png")

def test_force_player_scan():
    with patch("scripts.pwobs_scraper.run_scraper", new_callable=AsyncMock):
        response = client.post("/api/scan/players")
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Exception Branches (Coverage Boost)
# -------------------------------------------------------------

def test_get_player_exception():
    with patch("routers.api.get_player_profile", side_effect=Exception("DB Error")):
        response = client.post("/api/get_player", json={"role_id": 123})
        assert response.json()["status"] == "error"
        assert "DB Error" in response.json()["message"]

def test_queue_join_exception():
    with patch("routers.api.queue_manager.join_queue", side_effect=Exception("DB Error")):
        response = client.post("/api/queue/join", json={"user_id": 1, "queue_id": 2, "character_name": "Hero"})
        assert response.json()["status"] == "error"

def test_party_add_exception():
    with patch("routers.api.party_manager.add_to_party", side_effect=Exception("DB Error")):
        response = client.post("/api/party/add", json={"leader_role_id": 1, "nickname": "Hero"})
        assert response.json()["status"] == "error"

def test_character_link_missing():
    response = client.post("/api/character/link", json={"user_id": 1})
    assert response.json()["status"] == "error"

def test_character_link_exception():
    with patch("aiosqlite.connect", side_effect=Exception("DB Error")):
        response = client.post("/api/character/link", json={"user_id": 100, "nickname": "Test"})
        assert response.json()["status"] == "error"
