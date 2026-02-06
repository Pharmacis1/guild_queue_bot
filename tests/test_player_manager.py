import aiosqlite
import pytest

from logic.player_manager import update_player_logic


# Helper to seed DB
async def seed_player(db_path, role_id, nick):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("INSERT INTO players (role_id, nickname, in_clan) VALUES (?, ?, 1)", (role_id, nick))
        await conn.commit()


async def seed_user(db_path, telegram_id, username):
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("INSERT INTO users (telegram_id, username) VALUES (?, ?)", (telegram_id, username))
        await conn.commit()  # Fix: Ensure committed
        async with conn.execute("SELECT last_insert_rowid()") as cursor:
            return (await cursor.fetchone())[0]


@pytest.mark.asyncio
async def test_update_basic_info(test_db_session):
    db_path = test_db_session  # This string path is the DB

    # Seed
    await seed_player(db_path, 101, "OldNick")

    # Update
    result = await update_player_logic(
        101,
        {
            "nickname": "NewNick",
            "class_id": 5,  # Assassin
            "in_clan": False,
        },
        db_path=db_path,
    )

    assert result["status"] == "ok"

    # Verify
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT nickname, class_id, in_clan FROM players WHERE role_id=101") as cursor:
            row = await cursor.fetchone()
            assert row[0] == "NewNick"
            assert row[1] == 5
            assert row[2] == 0


@pytest.mark.asyncio
async def test_link_user_and_fail_invalid_tg(test_db_session):
    db_path = test_db_session
    await seed_player(db_path, 102, "LinkMe")

    # 1. Try linking non-existent user
    with pytest.raises(ValueError, match="User with TG ID 999999 not found"):
        await update_player_logic(102, {"telegram_id": 999999}, db_path=db_path)

    # 2. Seed User
    uid = await seed_user(db_path, 12345, "testuser")

    # 3. Link Success
    res = await update_player_logic(102, {"telegram_id": 12345}, db_path=db_path)
    assert res["status"] == "ok"

    # Verify Player has User ID
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT user_id FROM players WHERE role_id=102") as cursor:
            assert (await cursor.fetchone())[0] == uid


@pytest.mark.asyncio
async def test_bot_sync_is_main(test_db_session):
    """
    Test that linking a user + setting is_alt=False makes them MAIN in 'characters' table.
    """
    db_path = test_db_session
    uid = await seed_user(db_path, 22222, "master")
    await seed_player(db_path, 103, "MyChar")

    # Update: Link user, set as MAIN (is_alt=False)
    await update_player_logic(103, {"telegram_id": 22222, "is_alt": False}, db_path=db_path)

    async with aiosqlite.connect(db_path) as conn:
        # Check 'characters' (Bot Table)
        async with conn.execute("SELECT is_main, user_id FROM characters WHERE nickname='MyChar'") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 1  # is_main
            assert row[1] == uid


@pytest.mark.asyncio
async def test_afk_dates_update(test_db_session):
    db_path = test_db_session
    uid = await seed_user(db_path, 33333, "vacationer")
    await seed_player(db_path, 104, "AfkPlayer")

    # Provide ISO dates
    await update_player_logic(
        104, {"telegram_id": 33333, "afk_start": "2025-01-01T10:00", "afk_end": "2025-01-10T10:00"}, db_path=db_path
    )

    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT afk_start, afk_end FROM users WHERE id=?", (uid,)) as cursor:
            row = await cursor.fetchone()
            # It should preserve format or close to it
            assert "2025-01-01 10:00:00" == row[0]
