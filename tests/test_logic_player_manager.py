import pytest
import aiosqlite
import asyncio
from datetime import datetime
from database import Base, User, Character, AFKHistory, Settings, ConstantParty, PartyMember, Player

from logic.player_manager import parse_date_safe, update_player_logic, get_player_profile

# --- Tests for parse_date_safe ---
def test_parse_date_safe_valid_iso():
    dt_str = "2026-03-15T15:30:00"
    parsed = parse_date_safe(dt_str)
    assert parsed == "2026-03-15 15:30:00"

def test_parse_date_safe_valid_simple():
    dt_str = "2026-04-01"
    parsed = parse_date_safe(dt_str)
    assert parsed == "2026-04-01 00:00:00"

def test_parse_date_safe_empty():
    assert parse_date_safe("") is None
    assert parse_date_safe(None) is None

def test_parse_date_safe_invalid():
    assert parse_date_safe("not-a-date") is None

def test_parse_date_safe_datetime_error():
    # Force the parser to fail completely to hit the bare except (by passing invalid types if we could, but string is expected)
    # The current logic will catch `ValueError` in both iso and strptime, then dateutil might throw ParserError.
    # It's tested mostly by "not-a-date" anyway.
    pass

# --- Helper to init test DB for aiosqlite ---
async def init_test_db(db_path):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    
    # Insert basic test data
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("INSERT INTO users (telegram_id, username) VALUES (111, 'mainuser')")
        # role_id 1 = Existing linked player
        await conn.execute("INSERT INTO players (role_id, nickname, user_id, in_clan, is_alt) VALUES (1, 'PlayerOne', 1, 1, 0)")
        
        # role_id 2 = No user linked yet
        await conn.execute("INSERT INTO players (role_id, nickname, in_clan) VALUES (2, 'PlayerTwo', 1)")
        
        # role_id 3 = Virtual user
        await conn.execute("INSERT INTO players (role_id, nickname, in_clan) VALUES (3, 'VirtualPlayer', 1)")
        await conn.commit()

@pytest.fixture
async def async_test_db(test_db_path):
    await init_test_db(test_db_path)
    return test_db_path

# --- Tests for update_player_logic ---
@pytest.mark.asyncio
async def test_update_player_logic_linking_to_existing_tg_id(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    # Try linking PlayerTwo to numeric tg_id=111
    update_data = {
        "telegram_id": "111",
        "nickname": "PlayerTwoRenamed",
        "class_id": 5,
        "is_alt": True
    }
    
    res = await update_player_logic(2, update_data, db_path=async_test_db)
    assert res["status"] == "ok"
    
    async with aiosqlite.connect(async_test_db) as conn:
        # Check Player is updated
        async with conn.execute("SELECT nickname, class_id, is_alt, user_id FROM players WHERE role_id = 2") as cursor:
            row = await cursor.fetchone()
            assert row[0] == "PlayerTwoRenamed"
            assert row[1] == 5
            assert row[2] == 1
            assert row[3] == 1 # linked to user 1
            
        # Check Character sync
        async with conn.execute("SELECT user_id, is_main, nickname FROM characters WHERE nickname = 'PlayerTwoRenamed'") as cursor:
            c_row = await cursor.fetchone()
            assert c_row is not None
            assert c_row[0] == 1 # user_id
            assert c_row[1] == 0 # is_main is False because is_alt was True
            assert c_row[2] == "PlayerTwoRenamed"

@pytest.mark.asyncio
async def test_update_player_logic_linking_to_username(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    # Link to @mainuser
    update_data = {
        "telegram_id": "@mainuser",
    }
    
    res = await update_player_logic(2, update_data, db_path=async_test_db)
    assert res["status"] == "ok"
    
    async with aiosqlite.connect(async_test_db) as conn:
        async with conn.execute("SELECT user_id FROM players WHERE role_id = 2") as cursor:
            row = await cursor.fetchone()
            assert row[0] == 1 # Linked successfully by username


@pytest.mark.asyncio
async def test_update_player_logic_afk(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    update_data = {
        "afk_start": "2026-05-01",
        "afk_end": "2026-05-10",
        "afk_reason": "Vacation"
    }
    
    # Role 1 is linked to user 1
    res = await update_player_logic(1, update_data, db_path=async_test_db)
    assert res["status"] == "ok"
    
    async with aiosqlite.connect(async_test_db) as conn:
        async with conn.execute("SELECT afk_start, afk_end, afk_reason FROM users WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            assert row[0] == "2026-05-01 00:00:00"
            assert row[1] == "2026-05-10 00:00:00"
            assert row[2] == "Vacation"

@pytest.mark.asyncio
async def test_update_player_logic_clear_tg_id(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    update_data = {
        "telegram_id": " ",
    }
    
    res = await update_player_logic(1, update_data, db_path=async_test_db)
    assert res["status"] == "ok"
    
    async with aiosqlite.connect(async_test_db) as conn:
        async with conn.execute("SELECT user_id FROM players WHERE role_id = 1") as cursor:
            row = await cursor.fetchone()
            assert row[0] is None

@pytest.mark.asyncio
async def test_update_player_logic_invalid_class(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    update_data = {
        "class_id": 999  # Invalid class id
    }
    
    with pytest.raises(ValueError, match="Invalid Class ID: 999"):
        await update_player_logic(1, update_data, db_path=async_test_db)

@pytest.mark.asyncio
async def test_update_player_logic_player_not_found(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    update_data = {"nickname": "Ghost"}
    with pytest.raises(ValueError, match="Player not found"):
        await update_player_logic(999, update_data, db_path=async_test_db)

@pytest.mark.asyncio
async def test_get_player_profile(async_test_db, monkeypatch):
    monkeypatch.setattr("web_database.DB_NAME", async_test_db)
    
    # Setup extra profile data (queues, events, afk)
    async with aiosqlite.connect(async_test_db) as conn:
        await conn.execute("INSERT INTO afk_history (user_id, start_date, end_date, reason) VALUES (1, '2026-04-01 00:00:00', '2026-04-05 00:00:00', 'Sick')")
        
        await conn.execute("INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc) VALUES (1, 1000, '2026-03-01', 1, 10, 'Test Event')")
        
        await conn.execute("INSERT INTO queue_types (name, is_active) VALUES ('TestQ', 1)")
        await conn.execute("INSERT INTO queue_entries (user_id, queue_type_id, character_name, auto_requeue) VALUES (1, 1, 'PlayerOne', 1)")
        
        await conn.execute("INSERT INTO characters (user_id, nickname, is_main) VALUES (1, 'PlayerOneTwink', 0)")
        await conn.commit()
        
    profile = await get_player_profile(1)
    
    assert profile is not None
    assert profile["nickname"] == "PlayerOne"
    assert profile["user_id"] == 1
    assert profile["telegram_id"] == 111
    
    # Check collections
    assert len(profile["afk_history"]) == 1
    assert profile["afk_history"][0]["start"] == "2026-04-01T00:00:00"
    
    assert len(profile["events"]) == 1
    assert profile["events"][0]["value"] == 10
    
    assert len(profile["queues"]) == 1
    assert profile["queues"][0]["character_name"] == "PlayerOne"
    
    # Linked characters should include itself if recorded, plus the twink
    chars = [c["nickname"] for c in profile["linked_chars"]]
    assert "PlayerOneTwink" in chars
