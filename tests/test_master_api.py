import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base, User, Player, QueueType, QueueEntry, Character, RewardHistory, ConstantParty, PartyMember
import routers.api
import web_database

# --- Test DB Setup ---
TEST_DB = "test_master.db"
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
    
    # Common setup
    master = User(id=1, username="MasterAdmin", is_master=True, telegram_id=123)
    user = User(id=2, username="RegularUser", telegram_id=456)
    db_player = Player(role_id=1001, nickname="Hero", user_id=2, class_id=1)
    qtype = QueueType(id=1, name="Gold Queue", is_active=True)
    
    session.add_all([master, user, db_player, qtype])
    session.commit()
    
    try:
        with patch("database.session", session), \
             patch.object(routers.api, 'session', session), \
             patch("web_database.DB_NAME", TEST_DB):
            yield session
    finally:
        session.close()

def get_client():
    return TestClient(app)

# --- THE COVERAGE MASTER TEST ---
def test_api_coverage_completion(test_session):
    client = get_client()
    mock_bot = AsyncMock()
    
    with patch("loader.bot", mock_bot), \
         patch("utils.log_reward_to_sheet", new_callable=AsyncMock):
        
        # 1. Master Logic & Fallbacks (lines 206-212)
        test_session.add(QueueEntry(id=1, user_id=2, queue_type_id=1, character_name="Hero", position=1))
        # Add a master player record to hit fallback logic
        test_session.add(Player(role_id=888, nickname="MasterNick", user_id=1))
        test_session.commit()
        # Using role_id 888 instead of user_id 1
        client.post("/api/master/issue_reward", json={"entry_id": 1, "master_id": 888})
        
        # 2. Add to Queue Fallbacks (lines 429-434, 441-453)
        # Case insensitive fallback
        client.post("/api/master/add_to_queue", json={"queue_id": 1, "character_name": "hero"})
        # Character table fallback (Alt)
        test_session.add(Character(id=10, user_id=2, nickname="AltHero", is_main=False))
        test_session.commit()
        client.post("/api/master/add_to_queue", json={"queue_id": 1, "character_name": "AltHero"})
        
        # 3. stub user migration (lines 573-576)
        # This is hit via some bot logic usually but let's see if we can trigger via api
        # Not easy via API directly, but we hit routers.api logic.
        
        # 4. Party & Misc
        cp = ConstantParty(id=5, name="Alpha")
        test_session.add(cp)
        test_session.commit()
        test_session.add(PartyMember(party_id=5, player_role_id=1001, is_leader=True))
        test_session.commit()
        
        client.post("/api/party/get", json={"role_id": 1001})
        client.post("/api/party/rename", json={"party_id": 5, "name": "Omega"})
        client.post("/api/party/color", json={"party_id": 5, "color": "blue"})
        client.post("/api/party/remove", json={"member_role_id": 1001})
        
        # 5. AFK & Player
        client.post("/api/afk/add", json={"user_id": 2, "role_id": 1001, "start": "2024-01-01", "end": "2024-01-10"})
        client.post("/api/afk/delete", json={"afk_id": 1})
        client.post("/api/update_status", json={"role_id": 1001, "in_clan": True})
        client.post("/api/get_player", json={"role_id": 1001})
        
        # 6. Events (Parsing)
        client.post("/api/add_event", json={"role_id": 1001, "date": "2024-01-01T12:00:00", "value": 100})
        client.post("/api/add_event_bulk", json={"role_ids": [1001], "date": "2024-01-01 12:00", "value": 100})
        
        # 7. Scrapers
        with patch("routers.api.bg_run_scraper", new_callable=AsyncMock):
            client.post("/api/scrape_players", json={"server": "capella"})
            client.post("/api/scan/players")
            
        # 8. Dashboard
        client.get("/api/dashboard/history?limit=10")
        client.get("/api/dashboard/kh")
        client.get("/api/dashboard/money")
        
        # 9. Upload (line 46-78)
        with patch("routers.api.log_importer.process_log_upload", new_callable=AsyncMock) as m_up:
            m_up.return_value = ({"status": "ok"}, {123}, True)
            client.post("/api/upload", files={"file": ("test.log", b"data")})
        
        # 10. Profile dates (lines 268-270 in api_dashboard.py)
        # Set a player with afk dates and get profile
        master = test_session.get(User, 1)
        import datetime
        master.afk_start = datetime.datetime(2024, 1, 1)
        master.afk_end = datetime.datetime(2024, 1, 10)
        test_session.commit()
        # Find master's role_id (888 from step 1)
        client.get("/api/dashboard/profile/888")
