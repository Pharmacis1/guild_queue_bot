import pytest
import os
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from main import app
from database import Base, User, QueueType, RewardHistory, Settings
import routers.api
import web_database

# --- Test DB Setup ---
TEST_DB = "test_migrate.db"
engine_global = create_engine(f"sqlite:///{TEST_DB}")

@pytest.fixture(scope="module", autouse=True)
def setup_db_file():
    if os.path.exists(TEST_DB):
        try: os.remove(TEST_DB)
        except: pass
    Base.metadata.create_all(engine_global)
    yield
    engine_global.dispose()
    if os.path.exists(TEST_DB):
        try: os.remove(TEST_DB)
        except: pass

@pytest.fixture
def test_session():
    Session = sessionmaker(bind=engine_global)
    session = Session()
    # Clean tables
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    
    # Common setup
    master = User(id=1, username="MasterAdmin", is_master=True)
    user = User(id=2, username="RegularUser")
    qtype = QueueType(id=1, name="Test Queue", is_active=True, is_locked=False)
    
    session.add_all([master, user, qtype])
    session.commit()
    
    # Mocking standard session
    try:
        with patch("database.session", session), \
             patch.object(routers.api, 'session', session), \
             patch("web_database.DB_NAME", TEST_DB):
            yield session
    finally:
        session.close()

def get_client():
    return TestClient(app)

def test_master_settings(test_session):
    client = get_client()
    
    # 1. Get Settings
    res = client.get("/api/master/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["settings"]["default_limit"] == "1" # Default
    
    # 2. Update Settings
    res = client.post("/api/master/settings", json={"default_limit": 5})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # Verify
    res = client.get("/api/master/settings")
    assert res.json()["settings"]["default_limit"] == "5"

def test_user_limit(test_session):
    client = get_client()
    
    # Set personal limit for user (via user_id)
    res = client.post("/api/master/user_limit", json={"user_id": 2, "limit": 10})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # Verify in DB
    user = test_session.get(User, 2)
    assert user.personal_limit == 10

    # Set personal limit for player without user (via role_id)
    # Create a player without user_id
    from database import Player
    p = Player(role_id=123, nickname="UnlinkedHero", class_id=1)
    test_session.add(p)
    test_session.commit()

    res = client.post("/api/master/user_limit", json={"role_id": 123, "limit": 15})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Should have created a User and linked it
    p = test_session.get(Player, 123)
    assert p.user_id is not None
    user2 = test_session.get(User, p.user_id)
    assert user2.personal_limit == 15

def test_queue_description(test_session):
    client = get_client()
    
    res = client.post("/api/master/queue_description", json={"queue_id": 1, "description": "New conditions"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # Verify
    q = test_session.get(QueueType, 1)
    assert q.description == "New conditions"

def test_queue_lock(test_session):
    client = get_client()
    
    # Lock
    res = client.post("/api/master/queue_lock", json={"queue_id": 1, "is_locked": True})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # Verify
    q = test_session.get(QueueType, 1)
    assert q.is_locked == True
    
    # Unlock
    client.post("/api/master/queue_lock", json={"queue_id": 1, "is_locked": False})
    q = test_session.get(QueueType, 1)
    assert q.is_locked == False

def test_reward_history_mgmt(test_session):
    client = get_client()
    
    # Create some history
    h1 = RewardHistory(id=10, user_id=2, character_name="Hero", queue_name="Gold", issued_by="Master", timestamp=datetime.now())
    h2 = RewardHistory(id=11, user_id=2, character_name="Other", queue_name="Silver", issued_by="Admin", timestamp=datetime.now())
    test_session.add_all([h1, h2])
    test_session.commit()
    
    # 1. Fetch History
    res = client.get("/api/master/reward_history")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert len(data["history"]) == 2
    
    # 2. Filter by character
    res = client.get("/api/master/reward_history?character_name=Hero")
    assert len(res.json()["history"]) == 1
    
    # 3. Delete
    res = client.delete("/api/master/reward_history/10")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # Verify deletion
    res = client.get("/api/master/reward_history")
    assert len(res.json()["history"]) == 1
    assert res.json()["history"][0]["id"] == 11


def test_master_search_players_v2(test_session):
    client = get_client()
    # Search for an existing player (DevPlayer is created in conftest.py or setup)
    # If not sure about exact name, let's create one for safety
    from database import Player
    if not test_session.query(Player).filter_by(nickname="SearchHero").first():
        test_session.add(Player(role_id=1111, nickname="SearchHero", class_id=1))
        test_session.commit()

    res = client.post("/api/master/search_players", json={"query": "SearchHero"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    player = next(p for p in data["players"] if p["nickname"] == "SearchHero")
    assert "role_id" in player
    assert "has_telegram" in player
    assert "user_id" in player

def test_user_limit_shadow_creation(test_session):
    client = get_client()
    from database import Player, User
    
    # Create a player that doesn't have a user
    new_player = Player(role_id=999, nickname="ShadowHero", class_id=3)
    test_session.add(new_player)
    test_session.commit()
    
    # Set limit via role_id
    res = client.post("/api/master/user_limit", json={"role_id": 999, "limit": 7})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # Verify User was created and linked
    test_session.expire_all()
    p = test_session.get(Player, 999)
    assert p.user_id is not None
    user = test_session.get(User, p.user_id)
    assert user.personal_limit == 7
    assert user.username == "ShadowHero"

def test_history_suggestions(test_session):
    client = get_client()
    from database import RewardHistory
    import datetime
    
    # Add some history
    h1 = RewardHistory(user_id=1, character_name="HeroA", queue_name="QueueA", issued_by="MasterA", record_type="reward", timestamp=datetime.datetime.now())
    h2 = RewardHistory(user_id=2, character_name="HeroB", queue_name="QueueB", issued_by="MasterB", record_type="warning", timestamp=datetime.datetime.now())
    test_session.add_all([h1, h2])
    test_session.commit()
    
    res = client.get("/api/master/history_suggestions")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "QueueA" in data["queues"]
    assert "HeroA" in data["characters"]
    assert "MasterA" in data["masters"]

def test_listing_overrides_refined(test_session):
    client = get_client()
    from database import User, Player
    
    # User 2 has limit 10 (from first test if run in sequence, but let's ensure)
    u = test_session.get(User, 2)
    u.personal_limit = 20
    # Ensure player has nickname
    p = test_session.query(Player).filter_by(user_id=2).first()
    if not p:
        p = Player(role_id=222, nickname="NickName2", user_id=2, class_id=2)
        test_session.add(p)
    else:
        p.nickname = "NickName2"
    test_session.commit()
    
    res = client.get("/api/master/user_limits")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    user_data = next(u for u in data["users"] if u["id"] == 2)
    assert user_data["display_name"] == "NickName2"
    assert user_data["personal_limit"] == 20

def test_get_user_limits(test_session):
    client = get_client()
    
    # 1. Set limit for user
    client.post("/api/master/user_limit", json={"user_id": 2, "limit": 7})
    
    # 2. Get limits
    res = client.get("/api/master/user_limits")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert len(data["users"]) == 1
    assert data["users"][0]["id"] == 2
    assert data["users"][0]["personal_limit"] == 7
    
    # 3. Clear limit
    client.post("/api/master/user_limit", json={"user_id": 2, "limit": None})
    res = client.get("/api/master/user_limits")
    assert len(res.json()["users"]) == 0
