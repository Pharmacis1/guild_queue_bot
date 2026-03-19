import pytest
from datetime import datetime, timedelta
from sqlalchemy import select, func

from logic import helpers, reward_ops, queue_manager
from database import QueueEntry, QueueType, User, Character, RewardHistory, AsyncSessionLocal

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
    join_date_map = {1: (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d 15:30:00")}
    assert helpers.is_newcomer(1, join_date_map) is True

def test_is_newcomer_exception():
    join_date_map = {1: "Not-a-Date"}
    assert helpers.is_newcomer(1, join_date_map) is False

# --- logic/reward_ops.py ---

@pytest.mark.asyncio
async def test_issue_reward_not_found(async_test_session):
    success, msg, _ = await reward_ops.issue_reward(async_test_session, 9999, "Admin")
    assert success is False
    assert "Уже" in msg

@pytest.mark.asyncio
async def test_issue_reward_auto_requeue(async_test_session):
    # Setup
    u = User(id=300, telegram_id=300, username="User300")
    q = QueueType(id=30, name="Test Queue 30")
    async_test_session.add_all([u, q])
    await async_test_session.commit()
    
    entry = QueueEntry(id=300, user_id=300, queue_type_id=30, character_name="P1", auto_requeue=True, position=1)
    async_test_session.add(entry)
    await async_test_session.commit()
    
    # Action
    success, msg, history = await reward_ops.issue_reward(async_test_session, 300, "Admin")
    assert success is True
    
    # Verify
    await async_test_session.commit()
    stmt = select(QueueEntry).filter_by(user_id=300, queue_type_id=30)
    res = await async_test_session.execute(stmt)
    entries = res.scalars().all()
    assert len(entries) == 1
    assert entries[0].id != 300

@pytest.mark.asyncio
async def test_issue_reward_normal_leave(async_test_session):
    u = User(id=301, telegram_id=301, username="User301")
    q = QueueType(id=31, name="Test Queue 31")
    async_test_session.add_all([u, q])
    await async_test_session.commit()
    
    entry = QueueEntry(id=301, user_id=301, queue_type_id=31, character_name="P2", auto_requeue=False, position=1)
    async_test_session.add(entry)
    await async_test_session.commit()
    
    success, msg, _ = await reward_ops.issue_reward(async_test_session, 301, "Admin")
    assert success is True
    
    await async_test_session.commit()
    stmt = select(QueueEntry).filter_by(id=301)
    res = await async_test_session.execute(stmt)
    assert res.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_warn_user_not_found(async_test_session):
    success, msg, _ = await reward_ops.warn_user(async_test_session, 9999, "Admin")
    assert success is False

@pytest.mark.asyncio
async def test_warn_user_has_user(async_test_session):
    u = User(id=302, telegram_id=302, username="User302")
    q = QueueType(id=32, name="Test Queue 32")
    async_test_session.add_all([u, q])
    await async_test_session.commit()
    
    entry = QueueEntry(id=302, user_id=302, queue_type_id=32, character_name="P3", auto_requeue=False)
    async_test_session.add(entry)
    await async_test_session.commit()
    
    success, msg, history = await reward_ops.warn_user(async_test_session, 302, "Admin")
    assert success is True
    assert history.user_id == 302

# --- logic/queue_manager.py ---

@pytest.mark.asyncio
async def test_join_queue_success(async_test_session):
    q = QueueType(id=40, name="TestQ40", is_active=True)
    async_test_session.add(q)
    await async_test_session.commit()
    
    resp = await queue_manager.join_queue(400, 40, "NewPlayer", False)
    assert resp["status"] == "ok"
    
    await async_test_session.commit()
    result = await async_test_session.execute(select(QueueEntry).filter_by(user_id=400))
    assert result.scalar_one_or_none() is not None

@pytest.mark.asyncio
async def test_join_queue_duplicate(async_test_session):
    q = QueueType(id=41, name="TestQ41", is_active=True)
    e = QueueEntry(user_id=401, queue_type_id=41, character_name="Duplicate")
    async_test_session.add_all([q, e])
    await async_test_session.commit()
    
    resp = await queue_manager.join_queue(401, 41, "Duplicate", True)
    assert resp["status"] == "error"
    assert "уже записаны" in resp["message"]

@pytest.mark.asyncio
async def test_leave_queue_success(async_test_session):
    q = QueueType(id=42, name="TestQ42", is_active=True)
    e = QueueEntry(id=500, user_id=402, queue_type_id=42, character_name="Exit")
    async_test_session.add_all([q, e])
    await async_test_session.commit()
    
    resp = await queue_manager.leave_queue(500)
    assert resp["status"] == "ok"
    
    await async_test_session.commit()
    result = await async_test_session.execute(select(QueueEntry).filter_by(id=500))
    assert result.scalar_one_or_none() is None

@pytest.mark.asyncio
async def test_queue_exceptions(patch_async_session, monkeypatch):
    class MockErrorSession:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): raise Exception("DB Error")
        async def __aexit__(self, *args): pass
            
    monkeypatch.setattr("logic.queue_manager.AsyncSessionLocal", MockErrorSession)
    
    resp_join = await queue_manager.join_queue(999, 1, "Error", True)
    assert resp_join["status"] == "error"
    assert "DB Error" in resp_join["message"]
