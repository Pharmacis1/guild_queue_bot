import pytest
from sqlalchemy import select
from database import Player, User, Character
from logic.player_manager import update_player_logic


@pytest.mark.asyncio
async def test_update_basic_info(async_test_session):
    session = async_test_session

    # Seed
    p = Player(role_id=101, nickname="OldNick", in_clan=1)
    session.add(p)
    await session.commit()

    # Update
    result = await update_player_logic(
        session,
        101,
        {
            "nickname": "NewNick",
            "class_id": 5,  # Assassin
            "in_clan": False,
        }
    )

    assert result["status"] == "ok"

    # Verify
    await session.refresh(p)
    assert p.nickname == "NewNick"
    assert p.class_id == 5
    assert p.in_clan == 0


@pytest.mark.asyncio
async def test_link_user_and_fail_invalid_tg(async_test_session):
    session = async_test_session
    p = Player(role_id=102, nickname="LinkMe", in_clan=1)
    session.add(p)
    await session.commit()

    # 1. Provide an unknown TG ID - code should now create a STUB user
    res = await update_player_logic(session, 102, {"telegram_id": 999999})
    assert res["status"] == "ok"
    
    result = await session.execute(select(User).filter_by(telegram_id=999999))
    stub_user = result.scalar_one_or_none()
    assert stub_user is not None
    
    await session.refresh(p)
    assert p.user_id == stub_user.id

    # 2. Seed Real User
    real_user = User(telegram_id=12345, username="testuser")
    session.add(real_user)
    await session.commit()

    # 3. Link Success
    res = await update_player_logic(session, 102, {"telegram_id": 12345})
    assert res["status"] == "ok"

    # Verify Player has User ID
    await session.refresh(p)
    assert p.user_id == real_user.id


@pytest.mark.asyncio
async def test_bot_sync_is_main(async_test_session):
    """
    Test that linking a user + setting is_alt=False makes them MAIN in 'characters' table.
    """
    session = async_test_session
    u = User(telegram_id=22222, username="master")
    session.add(u)
    p = Player(role_id=103, nickname="MyChar", in_clan=1)
    session.add(p)
    await session.commit()

    # Update: Link user, set as MAIN (is_alt=False)
    await update_player_logic(session, 103, {"telegram_id": 22222, "is_alt": False})

    # Check 'characters' (Bot Table)
    result = await session.execute(select(Character).filter_by(nickname='MyChar'))
    char = result.scalar_one_or_none()
    assert char is not None
    assert char.is_main == 1
    assert char.user_id == u.id


@pytest.mark.asyncio
async def test_afk_dates_update(async_test_session):
    session = async_test_session
    u = User(telegram_id=33333, username="vacationer")
    session.add(u)
    p = Player(role_id=104, nickname="AfkPlayer", in_clan=1)
    session.add(p)
    await session.commit()

    # Provide ISO dates
    await update_player_logic(
        session,
        104,
        {"telegram_id": 33333, "afk_start": "2025-01-01T10:00", "afk_end": "2025-01-10T10:00"}
    )

    await session.refresh(u)
    # It should be a datetime object now in the DB
    assert u.afk_start.year == 2025
    assert u.afk_start.month == 1
    assert u.afk_start.day == 1
    assert u.afk_start.hour == 10
