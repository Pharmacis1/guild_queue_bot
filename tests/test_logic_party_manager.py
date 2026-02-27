import aiosqlite
import pytest
import os
import tempfile
import asyncio

from logic import party_manager

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
    """CREATE TABLE constant_parties (
        id INTEGER PRIMARY KEY, 
        name TEXT, 
        color TEXT
    )""",
    """CREATE TABLE party_members (
        party_id INTEGER, 
        player_role_id INTEGER,
        is_leader INTEGER
    )"""
]

@pytest.fixture
async def party_db_session(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    import web_database
    monkeypatch.setattr(web_database, "DB_NAME", path)
    
    async with aiosqlite.connect(path) as db:
        for stmt in DB_SCHEMA:
            await db.execute(stmt)
            
        # Seed players
        await db.execute("INSERT INTO players (role_id, nickname, class_id) VALUES (?, ?, ?)", (1, "Leader1", 1))
        await db.execute("INSERT INTO players (role_id, nickname, class_id) VALUES (?, ?, ?)", (2, "Member1", 2))
        await db.execute("INSERT INTO players (role_id, nickname, class_id) VALUES (?, ?, ?)", (3, "NoCP", 3))
        await db.execute("INSERT INTO players (role_id, nickname, class_id) VALUES (?, ?, ?)", (4, "Leader2", 4))
        await db.execute("INSERT INTO players (role_id, nickname, class_id) VALUES (?, ?, ?)", (5, "Member2", 5))
        
        # Seed Party 1 (Active, 2 members)
        await db.execute("INSERT INTO constant_parties (id, name, color) VALUES (?, ?, ?)", (1, "Alpha Team", "#FF0000"))
        await db.execute("INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, ?)", (1, 1, 1))
        await db.execute("INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, ?)", (1, 2, 0))

        # Seed Party 2 (Active, 1 member)
        await db.execute("INSERT INTO constant_parties (id, name, color) VALUES (?, ?, ?)", (2, "Beta Team", "#00FF00"))
        await db.execute("INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, ?)", (2, 4, 1))

        await db.commit()

    yield path
    
    os.remove(path)

# --- Tests ---

@pytest.mark.asyncio
async def test_get_party_empty(party_db_session):
    resp = await party_manager.get_party(3) # Player NoCP
    assert resp["status"] == "ok"
    assert resp["party"] is None
    assert len(resp["members"]) == 0

@pytest.mark.asyncio
async def test_get_party_populated(party_db_session):
    resp = await party_manager.get_party(1) # Leader1
    assert resp["status"] == "ok"
    assert resp["party"]["name"] == "Alpha Team"
    assert resp["party"]["is_leader"] is True
    assert len(resp["members"]) == 2
    
    # Leader should be sorted first
    assert resp["members"][0]["role_id"] == 1
    assert resp["members"][0]["is_leader"] is True

@pytest.mark.asyncio
async def test_add_to_party_leader_has_no_cp(party_db_session):
    # Role 3 has no CP. Let them add Role 5 (who also currently has no CP bindings here beyond existance).
    # Wait, Role 5 is 'Member2' and isn't in any CP yet.
    # Leader = 3, target = "Member2"
    resp = await party_manager.add_to_party(3, "Member2")
    assert resp["status"] == "ok"
    assert "добавлен" in resp["message"]

    # Verify CP was auto-created
    party_resp = await party_manager.get_party(3)
    assert party_resp["party"]["name"] is None # created with NULL name
    assert party_resp["party"]["is_leader"] is True
    assert len(party_resp["members"]) == 2

@pytest.mark.asyncio
async def test_add_to_party_existing_cp(party_db_session):
    # Leader = 1 (Alpha Team). Target = "NoCP"
    resp = await party_manager.add_to_party(1, "NoCP")
    assert resp["status"] == "ok"
    assert "добавлен" in resp["message"]

    party_resp = await party_manager.get_party(1)
    assert len(party_resp["members"]) == 3

@pytest.mark.asyncio
async def test_add_to_party_invalid_user(party_db_session):
    resp = await party_manager.add_to_party(1, "GhostUser")
    assert resp["status"] == "error"
    assert "не найден" in resp["message"]

@pytest.mark.asyncio
async def test_remove_from_party_normal_member(party_db_session):
    resp = await party_manager.remove_from_party(2) # Member1 leaves Alpha Team
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(1) # Leader1
    assert len(party_resp["members"]) == 1 # Just leader left

@pytest.mark.asyncio
async def test_remove_from_party_last_member(party_db_session):
    # Party 2 has only Role 4
    resp = await party_manager.remove_from_party(4)
    assert resp["status"] == "ok"
    
    import aiosqlite, web_database
    async with aiosqlite.connect(web_database.DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM constant_parties WHERE id = 2") as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 0 # CP should be deleted because count dropped to 0

@pytest.mark.asyncio
async def test_remove_from_party_invalid_user(party_db_session):
    resp = await party_manager.remove_from_party(3) # NoCP
    assert resp["status"] == "error"
    assert "не состоит" in resp["message"]

@pytest.mark.asyncio
async def test_rename_party(party_db_session):
    resp = await party_manager.rename_party(1, "Sigma Team")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(1)
    assert party_resp["party"]["name"] == "Sigma Team"

@pytest.mark.asyncio
async def test_rename_party_empty_drops_to_null(party_db_session):
    resp = await party_manager.rename_party(1, "   ")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(1)
    assert party_resp["party"]["name"] is None

@pytest.mark.asyncio
async def test_update_party_color(party_db_session):
    resp = await party_manager.update_party_color(1, "#123456")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(1)
    assert party_resp["party"]["color"] == "#123456"

@pytest.mark.asyncio
async def test_update_party_color_empty_drops_to_null(party_db_session):
    resp = await party_manager.update_party_color(1, "   ")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(1)
    assert party_resp["party"]["color"] is None

@pytest.mark.asyncio
async def test_transfer_leadership_valid(party_db_session):
    resp = await party_manager.transfer_leadership(1, 2) # Alpha Team limit, 1->2
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(2) # member 2 is now leader
    assert party_resp["party"]["is_leader"] is True
    
    # Leader 1 should be demoted
    party_resp_old = await party_manager.get_party(1)
    assert party_resp_old["party"]["is_leader"] is False

@pytest.mark.asyncio
async def test_transfer_leadership_invalid_target(party_db_session):
    resp = await party_manager.transfer_leadership(1, 3) # Role 3 is NoCP
    assert resp["status"] == "error"
    assert "не состоит" in resp["message"]

@pytest.mark.asyncio
async def test_error_handlers(party_db_session, monkeypatch):
    import web_database
    # Break the DB connection temporarily to trigger the exception blocks
    monkeypatch.setattr(web_database, "DB_NAME", "/invalid/path/that/does/not/exist.db")
    
    assert (await party_manager.get_party(1))["status"] == "error"
    assert (await party_manager.add_to_party(1, "Member2"))["status"] == "error"
    assert (await party_manager.remove_from_party(2))["status"] == "error"
    assert (await party_manager.rename_party(1, "A"))["status"] == "error"
    assert (await party_manager.update_party_color(1, "A"))["status"] == "error"
    assert (await party_manager.transfer_leadership(1, 2))["status"] == "error"
