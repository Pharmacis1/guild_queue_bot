import pytest
from datetime import datetime
from sqlalchemy import select
from database import User, Player, Character, AFKHistory, QueueType, QueueEntry
from logic.player_manager import parse_date_safe, update_player_logic, get_player_profile

# --- Tests for parse_date_safe ---
def test_parse_date_safe_valid_iso():
    dt_str = "2026-03-15T15:30:00"
    parsed = parse_date_safe(dt_str)
    assert isinstance(parsed, datetime)
    assert parsed.year == 2026
    assert parsed.month == 3
    assert parsed.day == 15

def test_parse_date_safe_valid_simple():
    dt_str = "2026-04-01"
    parsed = parse_date_safe(dt_str)
    assert isinstance(parsed, datetime)
    assert parsed.year == 2026
    assert parsed.month == 4
    assert parsed.day == 1

def test_parse_date_safe_empty():
    assert parse_date_safe("") is None
    assert parse_date_safe(None) is None

def test_parse_date_safe_invalid():
    assert parse_date_safe("not-a-date") is None

@pytest.fixture
async def seeded_player_session(async_test_session):
    session = async_test_session
    
    # 1. Users
    u1 = User(id=1, telegram_id=111, username="mainuser")
    session.add(u1)
    await session.flush()
    
    # 2. Players
    p1 = Player(role_id=1, nickname="PlayerOne", user_id=1, in_clan=1, is_alt=False)
    p2 = Player(role_id=2, nickname="PlayerTwo", in_clan=1, is_alt=False)
    p3 = Player(role_id=3, nickname="VirtualPlayer", in_clan=1, is_alt=False)
    session.add_all([p1, p2, p3])
    
    await session.commit()
    yield session

# --- Tests for update_player_logic ---
@pytest.mark.asyncio
async def test_update_player_logic_linking_to_existing_tg_id(seeded_player_session):
    session = seeded_player_session
    
    update_data = {
        "telegram_id": "111",
        "nickname": "PlayerTwoRenamed",
        "class_id": 5,
        "is_alt": True
    }
    res = await update_player_logic(session, 2, update_data)
    assert res["status"] == "ok"
    
    # Verify Player is updated
    stmt = select(Player).where(Player.role_id == 2)
    p_updated = (await session.execute(stmt)).scalar_one()
    assert p_updated.nickname == "PlayerTwoRenamed"
    assert p_updated.class_id == 5
    assert p_updated.is_alt
    assert p_updated.user_id == 1
    
    # Check Character sync
    stmt_c = select(Character).where(Character.nickname == "PlayerTwoRenamed")
    c_updated = (await session.execute(stmt_c)).scalar_one()
    assert c_updated.user_id == 1
    assert c_updated.is_main is False

@pytest.mark.asyncio
async def test_update_player_logic_linking_to_username(seeded_player_session):
    session = seeded_player_session
    update_data = {"telegram_id": "@mainuser"}
    
    res = await update_player_logic(session, 2, update_data)
    assert res["status"] == "ok"
    
    stmt = select(Player).where(Player.role_id == 2)
    p_updated = (await session.execute(stmt)).scalar_one()
    assert p_updated.user_id == 1

@pytest.mark.asyncio
async def test_update_player_logic_afk(seeded_player_session):
    session = seeded_player_session
    update_data = {
        "afk_start": "2026-05-01",
        "afk_end": "2026-05-10",
        "afk_reason": "Vacation"
    }
    
    res = await update_player_logic(session, 1, update_data)
    assert res["status"] == "ok"
    
    stmt = select(User).where(User.id == 1)
    u_updated = (await session.execute(stmt)).scalar_one()
    assert u_updated.afk_start.year == 2026
    assert u_updated.afk_start.month == 5
    assert u_updated.afk_reason == "Vacation"

@pytest.mark.asyncio
async def test_update_player_logic_clear_tg_id(seeded_player_session):
    session = seeded_player_session
    update_data = {"telegram_id": " "}
    
    res = await update_player_logic(session, 1, update_data)
    assert res["status"] == "ok"
    
    stmt = select(Player).where(Player.role_id == 1)
    p_updated = (await session.execute(stmt)).scalar_one()
    assert p_updated.user_id is None

@pytest.mark.asyncio
async def test_update_player_logic_invalid_class(seeded_player_session):
    session = seeded_player_session
    update_data = {"class_id": 999}
    
    res = await update_player_logic(session, 1, update_data)
    assert res["status"] == "error"
    assert "Invalid Class ID: 999" in res["message"]

@pytest.mark.asyncio
async def test_update_player_logic_player_not_found(seeded_player_session):
    session = seeded_player_session
    update_data = {"nickname": "Ghost"}
    
    res = await update_player_logic(session, 999, update_data)
    assert res["status"] == "error"
    assert "Player not found" in res["message"]

@pytest.mark.asyncio
async def test_get_player_profile(seeded_player_session):
    session = seeded_player_session
    
    # Setup extra profile data
    h1 = AFKHistory(user_id=1, start_date=datetime(2026, 4, 1), end_date=datetime(2026, 4, 5), reason="Sick")
    session.add(h1)
    
    qt = QueueType(id=1, name="TestQ", is_active=True)
    session.add(qt)
    await session.flush()
    
    qe = QueueEntry(user_id=1, queue_type_id=1, character_name="PlayerOne", auto_requeue=True)
    session.add(qe)
    
    c1 = Character(user_id=1, nickname="PlayerOneTwink", is_main=False)
    session.add(c1)
    
    await session.commit()
    
    profile = await get_player_profile(session, 1)
    
    assert profile is not None
    assert profile["nickname"] == "PlayerOne"
    assert profile["user_id"] == 1
    assert profile["telegram_id"] == 111
    
    assert len(profile["afk_history"]) == 1
    assert "01.04.2026" in profile["afk_history"][0]["start"]
    
    assert len(profile["queues"]) == 1, "Queues length should be 1"
    assert profile["queues"][0]["character_name"] == "PlayerOne", "Queue character name mismatch"
    
    chars = [c["nickname"] for c in profile["linked_chars"]]
    assert "PlayerOneTwink" in chars, f"PlayerOneTwink missing from {chars}"
