import pytest
import datetime
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from main import app
from database import User, Player, QueueType, QueueEntry, Character, AFKHistory

@pytest.fixture
async def test_session(async_test_session):
    session = async_test_session
    
    # Common setup: A master user to bypass auth (mocked)
    master = User(id=1, username="MasterAdmin", is_master=True, telegram_id=123)
    # A linked user and player
    user2 = User(id=2, username="LinkedUser", telegram_id=456)
    player2 = Player(role_id=1002, nickname="LinkedPlayer", user_id=2, class_id=1)
    char2 = Character(id=1002, user_id=2, nickname="LinkedPlayer", is_main=True)
    
    # An unlinked player
    player3 = Player(role_id=1003, nickname="UnlinkedPlayer", user_id=None, class_id=2)
    
    qtype = QueueType(id=1, name="Gold Queue", is_active=True)
    
    session.add_all([master, user2, player2, char2, player3, qtype])
    await session.commit()
    
    # Apply patches for routers and get_current_user
    with patch("routers.api.get_current_user", return_value=master):
        yield session

@pytest.mark.asyncio
async def test_afk_sync_linked_user(test_session):
    """Test that saving AFK status for a linked user updates both User and Player tables."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        start_date = "2024-05-01"
        end_date = "2024-05-10"
        
        # Save AFK for LinkedUser (id=2)
        response = await ac.post("/api/master/afk/save", json={
            "user_id": 2,
            "start": start_date,
            "end": end_date,
            "reason": "Vacation"
        })
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # Verify User table
        result = await test_session.execute(select(User).filter_by(id=2))
        u = result.scalar_one()
        assert u.afk_start.strftime("%Y-%m-%d") == start_date
        assert u.afk_reason == "Vacation"
        
        # Verify Player table (Synchronization)
        result = await test_session.execute(select(Player).filter_by(user_id=2))
        p = result.scalar_one()
        assert p.afk_start.strftime("%Y-%m-%d") == start_date
        assert p.afk_reason == "Vacation"
        
        # Verify AFKHistory
        result = await test_session.execute(select(AFKHistory).filter_by(user_id=2))
        history = result.scalar_one()
        assert history.reason == "Vacation"

@pytest.mark.asyncio
async def test_afk_sync_unlinked_player(test_session):
    """Test that saving AFK status for an unlinked player updates the Player table and history."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        start_date = "2024-06-01"
        end_date = "2024-06-05"
        
        # Save AFK for UnlinkedPlayer (role_id=1003)
        response = await ac.post("/api/master/afk/save", json={
            "role_id": 1003,
            "start": start_date,
            "end": end_date,
            "reason": "Business trip"
        })
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # Verify Player table
        result = await test_session.execute(select(Player).filter_by(role_id=1003))
        p = result.scalar_one()
        assert p.afk_start.strftime("%Y-%m-%d") == start_date
        assert p.afk_reason == "Business trip"
        
        # Verify AFKHistory (via role_id)
        result = await test_session.execute(select(AFKHistory).filter_by(role_id=1003))
        history = result.scalar_one()
        assert history.reason == "Business trip"

@pytest.mark.asyncio
async def test_get_master_afk_combined(test_session):
    """Test that /master/afk returns players from both tables securely."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        now = datetime.datetime.now()
        start = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        end = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Set AFK for both types
        await ac.post("/api/master/afk/save", json={"user_id": 2, "start": start, "end": end, "reason": "Reason 1"})
        await ac.post("/api/master/afk/save", json={"role_id": 1003, "start": start, "end": end, "reason": "Reason 2"})
        
        response = await ac.get("/api/master/afk")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        players = data["afk_players"]
        
        # Should have 2 players
        assert len(players) == 2
        nicks = [p["nickname"] for p in players]
        assert "LinkedPlayer" in nicks
        assert "UnlinkedPlayer" in nicks

@pytest.mark.asyncio
async def test_master_afk_history_nicknames(test_session):
    """Test that history shows nicknames correctly for all types."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Add history records
        await ac.post("/api/master/afk/save", json={"user_id": 2, "start": "2024-01-01", "end": "2024-01-02", "reason": "H1"})
        await ac.post("/api/master/afk/save", json={"role_id": 1003, "start": "2024-01-03", "end": "2024-01-04", "reason": "H2"})
        
        response = await ac.get("/api/master/afk/history")
        assert response.status_code == 200
        history = response.json()["history"]
        
        assert len(history) >= 2
        nicks = [h["nickname"] for h in history]
        assert "LinkedPlayer" in nicks
        assert "UnlinkedPlayer" in nicks

@pytest.mark.asyncio
async def test_toggle_auto_requeue(test_session):
    """Test the new toggle_auto_requeue endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Add a player to queue
        test_session.add(QueueEntry(id=50, queue_type_id=1, character_name="Tester", position=1, auto_requeue=False))
        await test_session.commit()
        
        # Toggle ON
        response = await ac.post("/api/master/toggle_auto_requeue", json={"entry_id": 50})
        assert response.status_code == 200
        assert response.json()["auto_requeue"] is True
        
        # Verify in DB
        result = await test_session.execute(select(QueueEntry).filter_by(id=50))
        entry = result.scalar_one()
        assert entry.auto_requeue is True
        
        # Toggle OFF
        response = await ac.post("/api/master/toggle_auto_requeue", json={"entry_id": 50})
        assert response.json()["auto_requeue"] is False
        
        # Reload to ensure we get the updated value from DB
        test_session.expire_all()
        result = await test_session.execute(select(QueueEntry).filter_by(id=50))
        entry = result.scalar_one()
        assert entry.auto_requeue is False

@pytest.mark.asyncio
async def test_add_to_queue_case_insensitive(test_session):
    """Test that adding to queue is case-insensitive and correctly pulls nickname."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Try adding "linkedplayer" (lowercase)
        response = await ac.post("/api/master/add_to_queue", json={
            "queue_id": 1,
            "character_name": "linkedplayer",
            "auto_requeue": True
        })
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # Verify in DB: should have the original casing "LinkedPlayer"
        result = await test_session.execute(select(QueueEntry).filter_by(queue_type_id=1))
        entry = result.scalar_one()
        assert entry.character_name == "LinkedPlayer"
        assert entry.auto_requeue is True
