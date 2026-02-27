import pytest
import aiosqlite
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from logic import helpers, reward_ops, queue_manager

# --- logic/helpers.py ---

def test_is_newcomer_valid():
    join_date_map = {1: (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")}
    assert helpers.is_newcomer(1, join_date_map) is True

def test_is_newcomer_older():
    join_date_map = {1: (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")}
    assert helpers.is_newcomer(1, join_date_map) is False

def test_is_newcomer_missing_or_invalid_id():
    join_date_map = {1: "2023-01-01"}
    assert helpers.is_newcomer(999, join_date_map) is False
    assert helpers.is_newcomer(None, join_date_map) is False

def test_is_newcomer_handles_time_format():
    # some dates come back as "2023-01-01 12:34:56"
    join_date_map = {1: (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 15:30:00")}
    assert helpers.is_newcomer(1, join_date_map) is True

def test_is_newcomer_exception():
    join_date_map = {1: "Not-a-Date"}
    # Should catch the ValueError and return False
    assert helpers.is_newcomer(1, join_date_map) is False

# --- logic/reward_ops.py ---

def test_issue_reward_not_found():
    mock_session = MagicMock()
    mock_session.get.return_value = None
    success, msg, _ = reward_ops.issue_reward(mock_session, 1, "Admin")
    assert success is False
    assert "Уже" in msg

def test_issue_reward_auto_requeue():
    mock_session = MagicMock()
    
    mock_entry = MagicMock()
    mock_entry.queue_type_id = 9
    mock_entry.queue.name = "Test Queue"
    mock_entry.character_name = "PlayerOne"
    mock_entry.user_id = 100
    mock_entry.auto_requeue = True
    
    mock_session.get.return_value = mock_entry
    
    success, msg, history = reward_ops.issue_reward(mock_session, 1, "Admin")
    assert success is True
    assert "Перезаписан" in msg
    assert history.character_name == "PlayerOne"
    # Ensure add and delete was called correctly
    assert mock_session.add.call_count == 2 # 1 for history, 1 for new queued entry
    mock_session.delete.assert_called_once_with(mock_entry)
    mock_session.commit.assert_called_once()

def test_issue_reward_normal_leave():
    mock_session = MagicMock()
    
    mock_entry = MagicMock()
    mock_entry.queue_type_id = 9
    mock_entry.queue.name = "Test Queue"
    mock_entry.character_name = "PlayerOne"
    mock_entry.user_id = 100
    mock_entry.auto_requeue = False
    
    mock_session.get.return_value = mock_entry
    
    success, msg, _ = reward_ops.issue_reward(mock_session, 1, "Admin")
    assert success is True
    assert "Ушел" in msg
    assert mock_session.add.call_count == 1 # Only history
    mock_session.delete.assert_called_once_with(mock_entry)

def test_warn_user_not_found():
    mock_session = MagicMock()
    mock_session.get.return_value = None
    success, msg, _ = reward_ops.warn_user(mock_session, 1, "Admin")
    assert success is False
    assert "не найдена" in msg

def test_warn_user_has_user():
    mock_session = MagicMock()
    
    mock_entry = MagicMock()
    mock_entry.user_id = 100
    mock_entry.character_name = "PlayerOne"
    mock_entry.queue.name = "Test Queue"

    mock_user = MagicMock()
    mock_user.id = 100
    
    # Session.get is called twice -> first for entry, second for user
    mock_session.get.side_effect = [mock_entry, mock_user]
    
    success, msg, history = reward_ops.warn_user(mock_session, 1, "Admin")
    assert success is True
    assert "в список рассылки" in msg
    assert history.user_id == 100
    assert history.record_type == "warning"
    mock_session.add.assert_called_once_with(history)

def test_warn_user_no_user_obj():
    mock_session = MagicMock()
    
    mock_entry = MagicMock()
    mock_entry.user_id = None # Orphaned entry test
    mock_entry.character_name = "PlayerOne"
    mock_entry.queue.name = "Test Queue"
    
    # Session.get returns entry, doesn't query user
    mock_session.get.side_effect = [mock_entry]
    
    success, msg, history = reward_ops.warn_user(mock_session, 1, "Admin")
    assert success is True
    assert "нет привязки" in msg
    assert history.user_id is None

# --- logic/queue_manager.py ---

DB_SCHEMA = [
    """CREATE TABLE queue_entries (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        queue_type_id INTEGER,
        character_name TEXT,
        auto_requeue INTEGER
    )"""
]

@pytest.fixture
async def queue_db_session(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    import web_database
    monkeypatch.setattr(web_database, "DB_NAME", path)
    
    async with aiosqlite.connect(path) as db:
        for stmt in DB_SCHEMA:
            await db.execute(stmt)
        
        # Seed an existing queue entry
        await db.execute("INSERT INTO queue_entries (id, user_id, queue_type_id, character_name, auto_requeue) VALUES (?, ?, ?, ?, ?)",
                         (1, 100, 1, "ExistingPlayer", 1))
        await db.commit()

    yield path
    os.remove(path)

@pytest.mark.asyncio
async def test_join_queue_success(queue_db_session):
    resp = await queue_manager.join_queue(101, 1, "NewPlayer", False)
    assert resp["status"] == "ok"
    
    import web_database
    async with aiosqlite.connect(web_database.DB_NAME) as db:
        async with db.execute("SELECT user_id, auto_requeue FROM queue_entries WHERE user_id = 101") as cur:
            row = await cur.fetchone()
            assert row[0] == 101
            assert row[1] == 0

@pytest.mark.asyncio
async def test_join_queue_duplicate(queue_db_session):
    # Try joining queue_type_id 1 with user_id 100 again
    resp = await queue_manager.join_queue(100, 1, "ExistingPlayer", True)
    assert resp["status"] == "error"
    assert "уже записаны" in resp["message"]

@pytest.mark.asyncio
async def test_leave_queue_success(queue_db_session):
    resp = await queue_manager.leave_queue(1)
    assert resp["status"] == "ok"
    
    import web_database
    async with aiosqlite.connect(web_database.DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM queue_entries WHERE id = 1") as cur:
            assert (await cur.fetchone())[0] == 0

@pytest.mark.asyncio
async def test_queue_exceptions(queue_db_session, monkeypatch):
    import web_database
    monkeypatch.setattr(web_database, "DB_NAME", "/invalid/path.db")
    
    resp_join = await queue_manager.join_queue(102, 1, "Error", True)
    assert resp_join["status"] == "error"
    
    resp_leave = await queue_manager.leave_queue(1)
    assert resp_leave["status"] == "error"
