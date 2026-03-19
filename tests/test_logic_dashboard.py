import pytest
from datetime import datetime
from database import User, Player, Character, AFKHistory, QueueType, QueueEntry, Item, Event, ConstantParty, PartyMember
from logic import dashboard

@pytest.fixture
async def seeded_dashboard_session(async_test_session):
    session = async_test_session
    
    # 1. Users
    u100 = User(id=100, telegram_id=111, username="mainuser", afk_start=datetime(2023, 10, 1), afk_end=datetime(2023, 10, 10), afk_reason="Vacation")
    u200 = User(id=200, telegram_id=222, username="unlinked")
    session.add_all([u100, u200])
    await session.flush()
    
    # 2. Players
    p1 = Player(role_id=1, user_id=100, nickname="Main1", in_clan=1, first_seen=datetime(2023, 1, 1, 12, 0), is_alt=False, class_id=1)
    p2 = Player(role_id=2, user_id=100, nickname="Alt1", in_clan=1, first_seen=datetime(2023, 1, 2, 12, 0), is_alt=True, class_id=2)
    p3 = Player(role_id=3, user_id=200, nickname="Unlinked", in_clan=1, first_seen=datetime(2023, 6, 1), is_alt=False, class_id=3)
    p4 = Player(role_id=4, user_id=None, nickname="NoUser", in_clan=1, first_seen=datetime(2023, 6, 1), is_alt=False, class_id=4)
    session.add_all([p1, p2, p3, p4])
    
    # 3. Characters
    c1 = Character(user_id=100, nickname="Main1", is_main=True)
    c2 = Character(user_id=100, nickname="Alt1", is_main=False)
    session.add_all([c1, c2])

    # 4. AFK History
    h1 = AFKHistory(role_id=3, start_date=datetime(2023, 11, 1), end_date=datetime(2023, 11, 5), reason="Sick")
    session.add(h1)
    
    # 5. Constant Party
    cp1 = ConstantParty(id=1, name="Alpha Team", color="#FF0000")
    session.add(cp1)
    await session.flush()
    pm1 = PartyMember(party_id=1, player_role_id=1)
    session.add(pm1)

    # 6. Events & Items
    it1 = Item(id=1, name="Sword")
    session.add(it1)
    await session.flush()
    ev1 = Event(event_date="2023-10-05 10:00:00", event_type=0, value=1, role_id=3, raw_desc="Got ID 1", timestamp=1696492800)
    ev2 = Event(event_date="2023-10-06 10:00:00", event_type=1, value=100, role_id=1, raw_desc="Valor edit", timestamp=1696579200)
    session.add_all([ev1, ev2])

    await session.commit()
    yield session

# --- Test Shared Helpers ---

@pytest.mark.asyncio
async def test_get_join_dates(seeded_dashboard_session):
    join_dates, role_user_map = await dashboard.get_join_dates()
    
    assert 1 in join_dates
    # first_seen is datetime now
    assert join_dates[1].year == 2023
    
    # role_user_map logic linking
    assert role_user_map[1] == 100
    assert role_user_map[2] == 100 # twin linked
    assert role_user_map[3] == 200

@pytest.mark.asyncio
async def test_get_party_map(seeded_dashboard_session):
    party_map = await dashboard.get_party_map()
    assert 1 in party_map
    assert party_map[1][0]["name"] == "Alpha Team"

@pytest.mark.asyncio
async def test_get_main_nick_map(seeded_dashboard_session):
    main_nicks = await dashboard.get_main_nick_map()
    assert 2 in main_nicks # Alt1's main is Main1
    assert main_nicks[2] == "Main1"
    assert 1 not in main_nicks

@pytest.mark.asyncio
async def test_get_afk_map(seeded_dashboard_session):
    afk_map = await dashboard.get_afk_map()
    assert 100 in afk_map
    assert afk_map[100][0][2] == "Vacation"
    assert -3 in afk_map
    assert afk_map[-3][0][2] == "Sick"

@pytest.mark.asyncio
async def test_get_afk_display_info(seeded_dashboard_session):
    afk_map = await dashboard.get_afk_map()
    join_dates, role_user_map = await dashboard.get_join_dates()
    
    s_dt = datetime(2023, 10, 5)
    e_dt = datetime(2023, 10, 6)
    
    is_afk, txt, reason = dashboard.get_afk_display_info(1, role_user_map, afk_map, s_dt, e_dt)
    assert is_afk is True
    assert "Vacation" in reason

@pytest.mark.asyncio
async def test_get_history_data(seeded_dashboard_session):
    my_nicks = {"main1"}
    result = await dashboard.get_history_data("2023-10-01", "2023-10-10", [1, 2, 3], ["valor", "items"], my_nicks)
    assert len(result) == 2
    item_evt = next(r for r in result if r["type"] == 0)
    assert "Got Main1" in item_evt["desc"]
    val_evt = next(r for r in result if r["type"] == 1)
    assert val_evt["is_mine"] is True

@pytest.mark.asyncio
async def test_get_kh_table_data(seeded_dashboard_session, monkeypatch):
    async def mock_get_data(s, e, c, g_p, g_c, g_count=1):
        rows = [
            {"role_id": 1, "name": "Main1", "class_id": 1, "total_valor": 1000, "total_gold": 0, "is_alt": 0},
            {"role_id": 2, "name": "Alt1", "class_id": 2, "total_valor": -500, "total_gold": 1000, "is_alt": 1},
            {"role_id": 4, "name": "NoUser", "class_id": 4, "total_valor": 0, "total_gold": 0, "is_alt": 0}
        ]
        return rows, s, e, []
    
    monkeypatch.setattr("logic.dashboard.get_data_from_db", mock_get_data)
    my_nicks = {"main1"}
    ans = await dashboard.get_kh_table_data("2023-10-01", "2023-10-07", class_list=[1, 2], newcomers_mode="all", my_nicks=my_nicks)
    assert len(ans["rows"]) == 2

@pytest.mark.asyncio
async def test_get_money_table_data(seeded_dashboard_session, monkeypatch):
    async def mock_get_data(s, e, c, g_p, g_c):
        rows = [
            {
                "role_id": 1, "name": "Main1", "class_id": 1, "total_valor": 1000, "total_gold": 0, "is_alt": 0,
                "interval_stats": [{"start": datetime(2023, 10, 2), "end": datetime(2023, 10, 3)}]
            }
        ]
        return rows, s, e, []
    
    monkeypatch.setattr("logic.dashboard.get_data_from_db", mock_get_data)
    my_nicks = {"main1"}
    ans = await dashboard.get_money_table_data("2023-10-01", "2023-10-07", class_list=[1], newcomers_mode="all", group_period="daily", group_count=1, my_nicks=my_nicks)
    assert len(ans["rows"]) == 1
