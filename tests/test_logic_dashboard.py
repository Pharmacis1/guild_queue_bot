import aiosqlite
import pytest
import os
import tempfile
from datetime import datetime, timedelta
import asyncio

from logic import dashboard

# Mock Data helpers
DB_SCHEMA = [
    """CREATE TABLE players (
        role_id INTEGER PRIMARY KEY, 
        user_id INTEGER, 
        nickname TEXT, 
        in_clan INTEGER, 
        first_seen TEXT, 
        is_alt INTEGER, 
        class_id INTEGER
    )""",
    """CREATE TABLE characters (
        id INTEGER PRIMARY KEY, 
        user_id INTEGER, 
        nickname TEXT, 
        is_main INTEGER
    )""",
    """CREATE TABLE users (
        id INTEGER PRIMARY KEY, 
        afk_start TEXT, 
        afk_end TEXT, 
        afk_reason TEXT
    )""",
    """CREATE TABLE afk_history (
        id INTEGER PRIMARY KEY, 
        user_id INTEGER, 
        role_id INTEGER, 
        start_date TEXT, 
        end_date TEXT, 
        reason TEXT
    )""",
    """CREATE TABLE constant_parties (
        id INTEGER PRIMARY KEY, 
        name TEXT, 
        color TEXT
    )""",
    """CREATE TABLE party_members (
        party_id INTEGER, 
        player_role_id INTEGER
    )""",
    """CREATE TABLE events (
        id INTEGER PRIMARY KEY, 
        event_date TEXT, 
        event_type INTEGER, 
        value INTEGER, 
        role_id INTEGER, 
        raw_desc TEXT, 
        timestamp INTEGER
    )""",
    """CREATE TABLE items (
        id INTEGER PRIMARY KEY, 
        name TEXT
    )"""
]

@pytest.fixture
async def dashboard_db_session(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Patch the global DB_NAME
    monkeypatch.setattr(dashboard, "DB_NAME", path)
    
    async with aiosqlite.connect(path) as db:
        for stmt in DB_SCHEMA:
            await db.execute(stmt)
            
        # Seed players
        await db.execute("INSERT INTO players (role_id, user_id, nickname, in_clan, first_seen, is_alt, class_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (1, 100, "Main1", 1, "2023-01-01 12:00:00", 0, 1))
        await db.execute("INSERT INTO players (role_id, user_id, nickname, in_clan, first_seen, is_alt, class_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (2, 100, "Alt1", 1, "2023-01-02 12:00:00", 1, 2))
        await db.execute("INSERT INTO players (role_id, user_id, nickname, in_clan, first_seen, is_alt, class_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (3, 200, "Unlinked", 1, "2023-06-01", 0, 3))
        await db.execute("INSERT INTO players (role_id, user_id, nickname, in_clan, first_seen, is_alt, class_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (4, None, "NoUser", 1, "2023-06-01", 0, 4))
        
        # Seed characters
        await db.execute("INSERT INTO characters (user_id, nickname, is_main) VALUES (?, ?, ?)", (100, "Main1", 1))
        await db.execute("INSERT INTO characters (user_id, nickname, is_main) VALUES (?, ?, ?)", (100, "Alt1", 0))

        # Seed users (AFK)
        await db.execute("INSERT INTO users (id, afk_start, afk_end, afk_reason) VALUES (?, ?, ?, ?)", (100, "2023-10-01", "2023-10-10", "Vacation"))
        
        # Seed AFK history (Unlinked by User_ID fallback)
        await db.execute("INSERT INTO afk_history (user_id, role_id, start_date, end_date, reason) VALUES (?, ?, ?, ?, ?)", (None, 3, "2023-11-01", "2023-11-05", "Sick"))
        
        # Seed constant_parties
        await db.execute("INSERT INTO constant_parties (id, name, color) VALUES (?, ?, ?)", (1, "Alpha Team", "#FF0000"))
        await db.execute("INSERT INTO party_members (party_id, player_role_id) VALUES (?, ?)", (1, 1))

        # Seed events
        await db.execute("INSERT INTO items (id, name) VALUES (?, ?)", (1, "Sword"))
        await db.execute("INSERT INTO events (event_date, event_type, value, role_id, raw_desc, timestamp) VALUES (?, ?, ?, ?, ?, ?)", ("2023-10-05 10:00:00", 0, 1, 3, "Got ID 1", 1696492800))
        await db.execute("INSERT INTO events (event_date, event_type, value, role_id, raw_desc, timestamp) VALUES (?, ?, ?, ?, ?, ?)", ("2023-10-06 10:00:00", 1, 100, 1, "Valor edit", 1696579200))

        await db.commit()

    yield path
    
    os.remove(path)

# --- Test Shared Helpers ---

@pytest.mark.asyncio
async def test_get_join_dates(dashboard_db_session):
    join_dates, role_user_map = await dashboard.get_join_dates()
    
    assert 1 in join_dates
    assert join_dates[1] == "2023-01-01 12:00:00"
    
    # role_user_map logic linking via characters mapping
    assert role_user_map[1] == 100
    assert role_user_map[2] == 100 # twin linked
    assert role_user_map[3] == 200

@pytest.mark.asyncio
async def test_get_party_map(dashboard_db_session):
    party_map = await dashboard.get_party_map()
    assert 1 in party_map
    assert party_map[1][0]["name"] == "Alpha Team"

@pytest.mark.asyncio
async def test_get_main_nick_map(dashboard_db_session):
    main_nicks = await dashboard.get_main_nick_map()
    assert 2 in main_nicks # Alt1's main is Main1
    assert main_nicks[2] == "Main1"

    # 1 is Main, shouldn't be mapped
    assert 1 not in main_nicks
    assert 3 not in main_nicks

@pytest.mark.asyncio
async def test_get_afk_map(dashboard_db_session):
    afk_map = await dashboard.get_afk_map()
    
    # User 100 (Linked user with users table AFK)
    assert 100 in afk_map
    assert len(afk_map[100]) == 1
    assert afk_map[100][0][2] == "Vacation"
    
    # Role 3 (Unlinked player with role bound AFK)
    assert -3 in afk_map
    assert afk_map[-3][0][2] == "Sick"

@pytest.mark.asyncio
async def test_get_afk_display_info(dashboard_db_session):
    afk_map = await dashboard.get_afk_map()
    _, role_user_map = await dashboard.get_join_dates()
    
    s_dt = datetime(2023, 10, 5)
    e_dt = datetime(2023, 10, 6)
    
    # Overlap hit for User 100 (Role 1)
    is_afk, txt, reason = dashboard.get_afk_display_info(1, role_user_map, afk_map, s_dt, e_dt)
    assert is_afk is True
    assert "Vacation" in reason
    
    # No overlap
    s_dt2 = datetime(2023, 11, 10)
    e_dt2 = datetime(2023, 11, 12)
    is_afk2, _, _ = dashboard.get_afk_display_info(1, role_user_map, afk_map, s_dt2, e_dt2)
    assert is_afk2 is False

    # Overlap hit for unlinked Role 3
    s_dt3 = datetime(2023, 11, 2)
    is_afk3, _, rs = dashboard.get_afk_display_info(3, role_user_map, afk_map, s_dt3, s_dt3)
    assert is_afk3 is True
    assert "Sick" in rs


# --- Test Data Processors ---

@pytest.mark.asyncio
async def test_get_history_data(dashboard_db_session):
    # Has dynamic item ID replacement: "Got ID 1" -> "Got Main1"
    my_nicks = set(["main1"])
    result = await dashboard.get_history_data("2023-10-01", "2023-10-10", [1, 2, 3], ["valor", "items"], my_nicks)
    
    assert len(result) == 2
    
    # Check ID replacement dynamically!
    item_evt = next(r for r in result if r["type"] == 0)
    assert "Got Main1" in item_evt["desc"]
    
    # Check is_mine
    val_evt = next(r for r in result if r["type"] == 1)
    assert val_evt["is_mine"] is True

@pytest.mark.asyncio
async def test_get_kh_table_data(dashboard_db_session, monkeypatch):
    # Mock `get_data_from_db` because that represents a HUGE SQL View 
    # and we don't want to re-implement the exact aggregator view logic in test DB.
    async def mock_get_data(s, e, c, g_p, g_c):
        rows = [
            {"role_id": 1, "name": "Main1", "class_id": 1, "total_valor": 1000, "total_gold": 0, "is_alt": 0},
            {"role_id": 2, "name": "Alt1", "class_id": 2, "total_valor": -500, "total_gold": 1000, "is_alt": 1},
            {"role_id": 4, "name": "NoUser", "class_id": 4, "total_valor": 0, "total_gold": 0, "is_alt": 0}
        ]
        return rows, s, e, []
    
    monkeypatch.setattr(dashboard, "get_data_from_db", mock_get_data)
    
    my_nicks = {"main1"}
    
    # Normal request
    ans = await dashboard.get_kh_table_data("2023-10-01", "2023-10-07", class_list=[1, 2], newcomers_mode="all", my_nicks=my_nicks)
    
    assert len(ans["rows"]) == 2
    r_main = next(r for r in ans["rows"] if r["role_id"] == 1)
    assert r_main["is_mine"] is True
    assert r_main["valor_tier"] != ""
    assert r_main["is_afk"] is True # 2023-10-01 has AFK overlap

    # Fallback request
    ans2 = await dashboard.get_kh_table_data(None, None, class_list=None, newcomers_mode="hide", my_nicks=my_nicks)
    assert len(ans2["rows"]) > 0

@pytest.mark.asyncio
async def test_get_money_table_data(dashboard_db_session, monkeypatch):
    async def mock_get_data(s, e, c, g_p, g_c):
        rows = [
            {
                "role_id": 1, "name": "Main1", "class_id": 1, "total_valor": 1000, "total_gold": 0, "is_alt": 0,
                "interval_stats": [{"start": datetime(2023, 10, 2), "end": datetime(2023, 10, 3)}]
            },
            {
                "role_id": 4, "name": "NoUser", "class_id": 4, "total_valor": 0, "total_gold": 0, "is_alt": 0,
                "interval_stats": [{"start": datetime(2023, 5, 1), "end": datetime(2023, 5, 2)}] # Pre-join (before Jun 01)
            }
        ]
        return rows, s, e, []
    
    monkeypatch.setattr(dashboard, "get_data_from_db", mock_get_data)
    
    my_nicks = {"main1"}
    ans = await dashboard.get_money_table_data("2023-10-01", "2023-10-07", class_list=[1, 4], newcomers_mode="all", group_period="daily", group_count=1, my_nicks=my_nicks)
    assert len(ans["rows"]) == 2
    
    r_main = next(r for r in ans["rows"] if r["role_id"] == 1)
    # 2023-10-02 overlaps with AFK (10-01 to 10-10)
    assert r_main["interval_stats"][0]["is_afk_stay"] is True
    
    r_nouser = next(r for r in ans["rows"] if r["role_id"] == 4)
    # Pre-join overlap
    assert r_nouser["interval_stats"][0]["is_pre_join"] is True

    # Test fallback fallback ranges
    ans2 = await dashboard.get_money_table_data(None, None, [1], "hide", "weekly", 1, set())
    assert len(ans2["rows"]) == 1
