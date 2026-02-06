import aiosqlite
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

import web_database
from main import app


# Fixture to provide TestClient pointing to the app
@pytest_asyncio.fixture
async def client(test_db_session):
    # The test_db_session fixture (from conftest) ensures web_database.DB_NAME is patched
    # and the database is initialized.
    with TestClient(app) as c:
        yield c


@pytest.mark.asyncio
async def test_update_status_integration(client, test_db_session):
    """
    Test the /api/update_status endpoint which updates the 'in_clan' status.
    """
    # 1. Seed Initial State
    role_id = 801
    async with aiosqlite.connect(web_database.DB_NAME) as conn:
        # Create player with in_clan=1
        await conn.execute(
            "INSERT OR REPLACE INTO players (role_id, nickname, in_clan) VALUES (?, 'StatusTester', 1)", (role_id,)
        )
        await conn.commit()

    # 2. Call API to change status to 0 (Left Guild)
    response = client.post("/api/update_status", json={"role_id": role_id, "in_clan": False})

    # 3. Assert Response
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    # 4. Verify Database Update
    async with aiosqlite.connect(web_database.DB_NAME) as conn:
        async with conn.execute("SELECT in_clan FROM players WHERE role_id = ?", (role_id,)) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 0, "in_clan should be updated to 0"

    # 5. Call API to change status back to 1 (Returned)
    response = client.post("/api/update_status", json={"role_id": role_id, "in_clan": True})
    assert response.status_code == 200

    async with aiosqlite.connect(web_database.DB_NAME) as conn:
        async with conn.execute("SELECT in_clan FROM players WHERE role_id = ?", (role_id,)) as cursor:
            row = await cursor.fetchone()
            assert row[0] == 1, "in_clan should be updated to 1"


@pytest.mark.asyncio
async def test_update_player_integration(client, test_db_session):
    """
    Test the /api/update_player endpoint which handles complex logic:
    - Player Profile (Nick, Class)
    - User Linking (create User if needed)
    - Bot Character Sync
    """
    # 1. Seed Initial State
    role_id = 777
    original_nick = "HttpPlayer"
    async with aiosqlite.connect(web_database.DB_NAME) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO players (role_id, nickname, class_id) VALUES (?, ?, ?)", (role_id, original_nick, 0)
        )
        # Create a User only if we want to test linking to EXISTING user,
        # but the API can also link by creating? No, logic usually expects existing user for linking via UI logic?
        # Logic: "SELECT id FROM users WHERE telegram_id = ?" -> Must exist for linking.

        # Let's seed a User to link to
        await conn.execute("INSERT INTO users (telegram_id, username) VALUES (12345, 'TestUserTg')")
        await conn.commit()

    # 2. Prepare Update Payload
    # Change Nickname, Class, Link to User 12345
    payload = {
        "role_id": role_id,
        "nickname": "HttpUpdated",
        "class_id": 1,
        "is_alt": True,
        "telegram_id": 12345,  # Should link to existing user
        "afk_start": "2025-01-01",
        "afk_end": "2025-01-10",
    }

    # 3. Call API
    response = client.post("/api/update_player", json=payload)

    # 4. Assert Response
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok", f"API Error: {data.get('message')}"

    # 5. Verify Database
    async with aiosqlite.connect(web_database.DB_NAME) as conn:
        # Check Player Table
        async with conn.execute(
            "SELECT nickname, class_id, is_alt, user_id FROM players WHERE role_id=?", (role_id,)
        ) as cursor:
            p_row = await cursor.fetchone()
            assert p_row[0] == "HttpUpdated"
            assert p_row[1] == 1
            assert p_row[2] == 1  # is_alt=True
            user_id = p_row[3]
            assert user_id is not None

        # Check User Table (AFK Dates updated)
        async with conn.execute("SELECT afk_start, telegram_id FROM users WHERE id=?", (user_id,)) as cursor:
            u_row = await cursor.fetchone()
            assert u_row[1] == 12345
            # Date might be stored as string "2025-01-01 00:00:00" depending on logic
            assert str(u_row[0]).startswith("2025-01-01")

        # Check Characters Table (Sync)
        # Note: Logic creates a NEW entry in characters if name changed?
        # Logic: "UPDATE characters ... WHERE nickname = target_nick" IF exists, else INSERT
        # Since we renamed to HttpUpdated, and HttpUpdated NOT in chars -> INSERT.
        async with conn.execute("SELECT user_id, is_main FROM characters WHERE nickname='HttpUpdated'") as cursor:
            c_row = await cursor.fetchone()
            assert c_row[0] == user_id
            assert c_row[1] == 0  # is_alt=True implies is_main=False (logic specific)
