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
