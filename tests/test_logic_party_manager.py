import pytest
from sqlalchemy import select, func
from database import Player, ConstantParty, PartyMember
from logic import party_manager

@pytest.fixture
async def seeded_party_session(async_test_session):
    session = async_test_session
    
    # Seed players
    p1 = Player(role_id=1, nickname="Leader1", class_id=1)
    p2 = Player(role_id=2, nickname="Member1", class_id=2)
    p3 = Player(role_id=3, nickname="NoCP", class_id=3)
    p4 = Player(role_id=4, nickname="Leader2", class_id=4)
    p5 = Player(role_id=5, nickname="Member2", class_id=5)
    session.add_all([p1, p2, p3, p4, p5])
    
    # Seed Party 1 (Active, 2 members)
    cp1 = ConstantParty(id=1, name="Alpha Team", color="#FF0000")
    session.add(cp1)
    await session.flush()
    
    pm1 = PartyMember(party_id=1, player_role_id=1, is_leader=True)
    pm2 = PartyMember(party_id=1, player_role_id=2, is_leader=False)
    session.add_all([pm1, pm2])

    # Seed Party 2 (Active, 1 member)
    cp2 = ConstantParty(id=2, name="Beta Team", color="#00FF00")
    session.add(cp2)
    await session.flush()
    pm3 = PartyMember(party_id=2, player_role_id=4, is_leader=True)
    session.add(pm3)

    await session.commit()
    yield session

# --- Tests ---

@pytest.mark.asyncio
async def test_get_party_empty(seeded_party_session):
    resp = await party_manager.get_party(seeded_party_session, 3) # Player NoCP
    assert resp["status"] == "ok"
    assert resp["party"] is None
    assert len(resp["members"]) == 0

@pytest.mark.asyncio
async def test_get_party_populated(seeded_party_session):
    resp = await party_manager.get_party(seeded_party_session, 1) # Leader1
    assert resp["status"] == "ok"
    assert resp["party"]["name"] == "Alpha Team"
    assert resp["party"]["is_leader"] is True
    assert len(resp["members"]) == 2
    
    # Leader should be sorted first
    assert resp["members"][0]["role_id"] == 1
    assert resp["members"][0]["is_leader"] is True

@pytest.mark.asyncio
async def test_add_to_party_leader_has_no_cp(seeded_party_session):
    resp = await party_manager.add_to_party(seeded_party_session, 3, "Member2")
    assert resp["status"] == "ok"
    assert "добавлен" in resp["message"]

    # Verify CP was auto-created
    party_resp = await party_manager.get_party(seeded_party_session, 3)
    assert party_resp["party"]["name"] is None # created with NULL name
    assert party_resp["party"]["is_leader"] is True
    assert len(party_resp["members"]) == 2

@pytest.mark.asyncio
async def test_add_to_party_existing_cp(seeded_party_session):
    resp = await party_manager.add_to_party(seeded_party_session, 1, "NoCP")
    assert resp["status"] == "ok"
    assert "добавлен" in resp["message"]

    party_resp = await party_manager.get_party(seeded_party_session, 1)
    assert len(party_resp["members"]) == 3

@pytest.mark.asyncio
async def test_add_to_party_invalid_user(seeded_party_session):
    resp = await party_manager.add_to_party(seeded_party_session, 1, "GhostUser")
    assert resp["status"] == "error"
    assert "не найден" in resp["message"]

@pytest.mark.asyncio
async def test_remove_from_party_normal_member(seeded_party_session):
    resp = await party_manager.remove_from_party(seeded_party_session, 2) # Member1 leaves Alpha Team
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(seeded_party_session, 1) # Leader1
    assert len(party_resp["members"]) == 1 # Just leader left

@pytest.mark.asyncio
async def test_remove_from_party_last_member(seeded_party_session):
    # Party 2 has only Role 4
    resp = await party_manager.remove_from_party(seeded_party_session, 4)
    assert resp["status"] == "ok"
    
    result = await seeded_party_session.execute(select(func.count(ConstantParty.id)).where(ConstantParty.id == 2))
    assert result.scalar() == 0

@pytest.mark.asyncio
async def test_remove_from_party_invalid_user(seeded_party_session):
    resp = await party_manager.remove_from_party(seeded_party_session, 3) # NoCP
    assert resp["status"] == "error"
    assert "не состоит" in resp["message"]

@pytest.mark.asyncio
async def test_rename_party(seeded_party_session):
    resp = await party_manager.rename_party(seeded_party_session, 1, "Sigma Team")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(seeded_party_session, 1)
    assert party_resp["party"]["name"] == "Sigma Team"

@pytest.mark.asyncio
async def test_rename_party_empty_drops_to_null(seeded_party_session):
    resp = await party_manager.rename_party(seeded_party_session, 1, "   ")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(seeded_party_session, 1)
    assert party_resp["party"]["name"] is None

@pytest.mark.asyncio
async def test_update_party_color(seeded_party_session):
    resp = await party_manager.update_party_color(seeded_party_session, 1, "#123456")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(seeded_party_session, 1)
    assert party_resp["party"]["color"] == "#123456"

@pytest.mark.asyncio
async def test_update_party_color_empty_drops_to_null(seeded_party_session):
    resp = await party_manager.update_party_color(seeded_party_session, 1, "   ")
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(seeded_party_session, 1)
    assert party_resp["party"]["color"] is None

@pytest.mark.asyncio
async def test_transfer_leadership_valid(seeded_party_session):
    resp = await party_manager.transfer_leadership(seeded_party_session, 1, 2) # Alpha Team limit, 1->2
    assert resp["status"] == "ok"
    
    party_resp = await party_manager.get_party(seeded_party_session, 2) # member 2 is now leader
    assert party_resp["party"]["is_leader"] is True
    
    # Leader 1 should be demoted
    party_resp_old = await party_manager.get_party(seeded_party_session, 1)
    assert party_resp_old["party"]["is_leader"] is False

@pytest.mark.asyncio
async def test_transfer_leadership_invalid_target(seeded_party_session):
    resp = await party_manager.transfer_leadership(seeded_party_session, 1, 3) # Role 3 is NoCP
    assert resp["status"] == "error"
    assert "не состоит" in resp["message"]

@pytest.mark.asyncio
async def test_error_handlers(seeded_party_session, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    # Mocking session.execute to raise an exception
    from unittest.mock import AsyncMock
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = Exception("DB Error")
    mock_session.rollback = AsyncMock()
    
    assert (await party_manager.get_party(mock_session, 1))["status"] == "error"
    assert (await party_manager.add_to_party(mock_session, 1, "Member2"))["status"] == "error"
    assert (await party_manager.remove_from_party(mock_session, 2))["status"] == "error"
    assert (await party_manager.rename_party(mock_session, 1, "A"))["status"] == "error"
    assert (await party_manager.update_party_color(mock_session, 1, "A"))["status"] == "error"
    assert (await party_manager.transfer_leadership(mock_session, 1, 2))["status"] == "error"
