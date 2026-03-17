import pytest
import os
import datetime
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base, User, Player, QueueType, QueueEntry, Character, AFKHistory
import routers.api

# --- Test DB Setup ---
TEST_DB = "test_player_mgmt.db"
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
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    
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
    session.commit()
    
    # Apply patches to use this session
    with patch("database.session", session), \
         patch.object(routers.api, 'session', session), \
         patch("routers.api_dashboard.session", session), \
         patch("web_database.DB_NAME", TEST_DB), \
         patch("routers.api.get_current_user", return_value=master):
        yield session
    
    session.close()

def get_client():
    return TestClient(app)

# --- Test Cases ---

def test_afk_sync_linked_user(test_session):
    """Test that saving AFK status for a linked user updates both User and Player tables."""
    client = get_client()
    start_date = "2024-05-01"
    end_date = "2024-05-10"
    
    # Save AFK for LinkedUser (id=2)
    response = client.post("/api/master/afk/save", json={
        "user_id": 2,
        "start": start_date,
        "end": end_date,
        "reason": "Vacation"
    })
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Verify User table
    u = test_session.query(User).filter_by(id=2).first()
    assert u.afk_start.strftime("%Y-%m-%d") == start_date
    assert u.afk_reason == "Vacation"
    
    # Verify Player table (Synchronization)
    p = test_session.query(Player).filter_by(user_id=2).first()
    assert p.afk_start.strftime("%Y-%m-%d") == start_date
    assert p.afk_reason == "Vacation"
    
    # Verify AFKHistory
    history = test_session.query(AFKHistory).filter_by(user_id=2).first()
    assert history is not None
    assert history.reason == "Vacation"

def test_afk_sync_unlinked_player(test_session):
    """Test that saving AFK status for an unlinked player updates the Player table and history."""
    client = get_client()
    start_date = "2024-06-01"
    end_date = "2024-06-05"
    
    # Save AFK for UnlinkedPlayer (role_id=1003)
    response = client.post("/api/master/afk/save", json={
        "role_id": 1003,
        "start": start_date,
        "end": end_date,
        "reason": "Business trip"
    })
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Verify Player table
    p = test_session.query(Player).filter_by(role_id=1003).first()
    assert p.afk_start.strftime("%Y-%m-%d") == start_date
    assert p.afk_reason == "Business trip"
    
    # Verify AFKHistory (via role_id)
    history = test_session.query(AFKHistory).filter_by(role_id=1003).first()
    assert history is not None
    assert history.reason == "Business trip"

def test_get_master_afk_combined(test_session):
    """Test that /master/afk returns players from both tables securely."""
    client = get_client()
    now = datetime.datetime.now()
    start = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    end = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Set AFK for both types
    client.post("/api/master/afk/save", json={"user_id": 2, "start": start, "end": end, "reason": "Reason 1"})
    client.post("/api/master/afk/save", json={"role_id": 1003, "start": start, "end": end, "reason": "Reason 2"})
    
    response = client.get("/api/master/afk")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    players = data["afk_players"]
    
    # Should have 2 players
    assert len(players) == 2
    nicks = [p["nickname"] for p in players]
    assert "LinkedPlayer" in nicks
    assert "UnlinkedPlayer" in nicks

def test_master_afk_history_nicknames(test_session):
    """Test that history shows nicknames correctly for all types."""
    client = get_client()
    
    # Add history records
    client.post("/api/master/afk/save", json={"user_id": 2, "start": "2024-01-01", "end": "2024-01-02", "reason": "H1"})
    client.post("/api/master/afk/save", json={"role_id": 1003, "start": "2024-01-03", "end": "2024-01-04", "reason": "H2"})
    
    response = client.get("/api/master/afk/history")
    assert response.status_code == 200
    history = response.json()["history"]
    
    assert len(history) >= 2
    nicks = [h["nickname"] for h in history]
    assert "LinkedPlayer" in nicks
    assert "UnlinkedPlayer" in nicks

def test_toggle_auto_requeue(test_session):
    """Test the new toggle_auto_requeue endpoint."""
    client = get_client()
    
    # Add a player to queue
    test_session.add(QueueEntry(id=50, queue_type_id=1, character_name="Tester", position=1, auto_requeue=False))
    test_session.commit()
    
    # Toggle ON
    response = client.post("/api/master/toggle_auto_requeue", json={"entry_id": 50})
    assert response.status_code == 200
    assert response.json()["auto_requeue"] is True
    
    # Verify in DB
    entry = test_session.query(QueueEntry).filter_by(id=50).first()
    assert entry.auto_requeue is True
    
    # Toggle OFF
    response = client.post("/api/master/toggle_auto_requeue", json={"entry_id": 50})
    assert response.json()["auto_requeue"] is False
    assert test_session.query(QueueEntry).filter_by(id=50).first().auto_requeue is False

def test_add_to_queue_case_insensitive(test_session):
    """Test that adding to queue is case-insensitive and correctly pulls nickname."""
    client = get_client()
    
    # Try adding "linkedplayer" (lowercase)
    response = client.post("/api/master/add_to_queue", json={
        "queue_id": 1,
        "character_name": "linkedplayer",
        "auto_requeue": True
    })
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Verify in DB: should have the original casing "LinkedPlayer"
    entry = test_session.query(QueueEntry).filter_by(queue_type_id=1).first()
    assert entry.character_name == "LinkedPlayer"
    assert entry.auto_requeue is True
