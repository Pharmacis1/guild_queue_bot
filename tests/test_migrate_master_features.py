import pytest
from unittest.mock import patch, AsyncMock
from main import app
from database import User, QueueType, RewardHistory, Settings, Player
from httpx import AsyncClient, ASGITransport
from datetime import datetime

@pytest.mark.asyncio
async def test_master_settings(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial setup in the DB
        master = User(id=1, username="MasterAdmin", is_master=True)
        async_test_session.add(master)
        await async_test_session.commit()

        # 1. Get Settings
        res = await client.get("/api/master/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["settings"]["default_limit"] == "1" # Default
        
        # 2. Update Settings
        res = await client.post("/api/master/settings", json={"default_limit": 5})
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        
        # Verify
        res = await client.get("/api/master/settings")
        assert res.json()["settings"]["default_limit"] == "5"


@pytest.mark.asyncio
async def test_user_limit(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user = User(id=2, username="RegularUser")
        async_test_session.add(user)
        await async_test_session.commit()

        # Set personal limit for user (via user_id)
        res = await client.post("/api/master/user_limit", json={"user_id": 2, "limit": 10})
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        
        # Verify in DB
        await async_test_session.refresh(user)
        assert user.personal_limit == 10

        # Set personal limit for player without user (via role_id)
        p = Player(role_id=123, nickname="UnlinkedHero", class_id=1)
        async_test_session.add(p)
        await async_test_session.commit()

        res = await client.post("/api/master/user_limit", json={"role_id": 123, "limit": 15})
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # Should have created a User and linked it
        await async_test_session.refresh(p)
        assert p.user_id is not None
        user2 = await async_test_session.get(User, p.user_id)
        assert user2.personal_limit == 15


@pytest.mark.asyncio
async def test_queue_description(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        qtype = QueueType(id=1, name="Test Queue", is_active=True, is_locked=False)
        async_test_session.add(qtype)
        await async_test_session.commit()

        res = await client.post("/api/master/queue_description", json={"queue_id": 1, "description": "New conditions"})
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        
        # Verify
        await async_test_session.refresh(qtype)
        assert qtype.description == "New conditions"


@pytest.mark.asyncio
async def test_queue_lock(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        qtype = QueueType(id=1, name="Test Queue", is_active=True, is_locked=False)
        async_test_session.add(qtype)
        await async_test_session.commit()

        # Lock
        res = await client.post("/api/master/queue_lock", json={"queue_id": 1, "is_locked": True})
        assert res.status_code == 200
        
        # Verify
        await async_test_session.refresh(qtype)
        assert qtype.is_locked == True
        
        # Unlock
        await client.post("/api/master/queue_lock", json={"queue_id": 1, "is_locked": False})
        await async_test_session.refresh(qtype)
        assert qtype.is_locked == False


@pytest.mark.asyncio
async def test_reward_history_mgmt(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user = User(id=2, username="RegularUser")
        async_test_session.add(user)
        await async_test_session.commit()

        # Create some history
        h1 = RewardHistory(id=10, user_id=2, character_name="Hero", queue_name="Gold", issued_by="Master", timestamp=datetime.now())
        h2 = RewardHistory(id=11, user_id=2, character_name="Other", queue_name="Silver", issued_by="Admin", timestamp=datetime.now())
        async_test_session.add_all([h1, h2])
        await async_test_session.commit()
        
        # 1. Fetch History
        res = await client.get("/api/master/reward_history")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert len(data["history"]) == 2
        
        # 2. Filter by character
        res = await client.get("/api/master/reward_history?character_name=Hero")
        assert len(res.json()["history"]) == 1
        
        # 3. Delete
        res = await client.delete("/api/master/reward_history/10")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        
        # Verify deletion
        res = await client.get("/api/master/reward_history")
        assert len(res.json()["history"]) == 1
        assert res.json()["history"][0]["id"] == 11


@pytest.mark.asyncio
async def test_master_search_players_v2(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        p = Player(role_id=1111, nickname="SearchHero", class_id=1)
        async_test_session.add(p)
        await async_test_session.commit()

        res = await client.post("/api/master/search_players", json={"query": "SearchHero"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        player = next(p for p in data["players"] if p["nickname"] == "SearchHero")
        assert "role_id" in player


@pytest.mark.asyncio
async def test_user_limit_shadow_creation(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a player that doesn't have a user
        new_player = Player(role_id=999, nickname="ShadowHero", class_id=3)
        async_test_session.add(new_player)
        await async_test_session.commit()
        
        # Set limit via role_id
        res = await client.post("/api/master/user_limit", json={"role_id": 999, "limit": 7})
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        
        # Verify User was created and linked
        await async_test_session.refresh(new_player)
        assert new_player.user_id is not None
        user = await async_test_session.get(User, new_player.user_id)
        assert user.personal_limit == 7


@pytest.mark.asyncio
async def test_history_suggestions(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Add some history
        h1 = RewardHistory(user_id=1, character_name="HeroA", queue_name="QueueA", issued_by="MasterA", record_type="reward", timestamp=datetime.now())
        h2 = RewardHistory(user_id=2, character_name="HeroB", queue_name="QueueB", issued_by="MasterB", record_type="warning", timestamp=datetime.now())
        async_test_session.add_all([h1, h2])
        await async_test_session.commit()
        
        res = await client.get("/api/master/history_suggestions")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "QueueA" in data["queues"]


@pytest.mark.asyncio
async def test_listing_overrides_refined(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        u = User(id=2, username="User2", personal_limit=20)
        p = Player(role_id=222, nickname="NickName2", user_id=2, class_id=2)
        async_test_session.add_all([u, p])
        await async_test_session.commit()
        
        res = await client.get("/api/master/user_limits")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        user_data = next(u for u in data["users"] if u["id"] == 2)
        assert user_data["display_name"] == "NickName2"
        assert user_data["personal_limit"] == 20


@pytest.mark.asyncio
async def test_get_user_limits(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user = User(id=2, username="RegularUser")
        async_test_session.add(user)
        await async_test_session.commit()

        # 1. Set limit for user
        await client.post("/api/master/user_limit", json={"user_id": 2, "limit": 7})
        
        # 2. Get limits
        res = await client.get("/api/master/user_limits")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert any(u["id"] == 2 and u["personal_limit"] == 7 for u in data["users"])
        
        # 3. Clear limit
        await client.post("/api/master/user_limit", json={"user_id": 2, "limit": None})
        res = await client.get("/api/master/user_limits")
        assert not any(u["id"] == 2 for u in res.json()["users"])
