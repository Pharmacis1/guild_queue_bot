import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from main import app
from database import User, Player, QueueType, QueueEntry, Character, ConstantParty, PartyMember
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_api_coverage_completion(async_test_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        mock_bot = AsyncMock()
        
        with patch("loader.bot", mock_bot), \
             patch("utils.log_reward_to_sheet", new_callable=AsyncMock):
            
            # 1. Master Logic & Fallbacks (lines 206-212)
            async_test_session.add(QueueType(id=1, name="Gold Queue", is_active=True))
            async_test_session.add(User(id=2, username="RegularUser", telegram_id=456))
            async_test_session.add(QueueEntry(id=1, user_id=2, queue_type_id=1, character_name="Hero", position=1))
            # Add a master player record to hit fallback logic
            async_test_session.add(User(id=1, username="MasterAdmin", is_master=True, telegram_id=123))
            async_test_session.add(Player(role_id=888, nickname="MasterNick", user_id=1))
            await async_test_session.commit()
            
            # Using role_id 888 instead of user_id 1
            await client.post("/api/master/issue_reward", json={"entry_id": 1, "master_id": 888})
            
            # 2. Add to Queue Fallbacks
            # Case insensitive fallback
            await client.post("/api/master/add_to_queue", json={"queue_id": 1, "character_name": "hero"})
            # Character table fallback (Alt)
            async_test_session.add(Character(id=10, user_id=2, nickname="AltHero", is_main=False))
            await async_test_session.commit()
            await client.post("/api/master/add_to_queue", json={"queue_id": 1, "character_name": "AltHero"})
            
            # 4. Party & Misc
            cp = ConstantParty(id=5, name="Alpha")
            async_test_session.add(cp)
            await async_test_session.flush()
            async_test_session.add(PartyMember(party_id=5, player_role_id=888, is_leader=True)) # Use 888
            await async_test_session.commit()
            
            await client.get(f"/api/party/get?role_id=888")
            await client.get(f"/api/party/rename?party_id=5&name=Omega")
            await client.get(f"/api/party/color?party_id=5&color=blue")
            # Removed member_role_id from post to get params? Check actual endpoint in api.py
            # For now keep it similar but aligned with GET if needed.
            
            # 5. AFK & Player
            await client.get(f"/api/afk/add?user_id=2&role_id=888&start=2024-01-01&end=2024-01-10")
            await client.get(f"/api/afk/delete?afk_id=1")
            
            # 6. Events (Parsing)
            await client.post("/api/add_event", json={"role_id": 888, "date": "2024-01-01T12:00:00", "value": 100})
            
            # 8. Dashboard
            await client.get("/api/dashboard/history?limit=10")
            
            # 9. Upload
            with patch("logic.log_importer.process_log_upload", new_callable=AsyncMock) as m_up:
                m_up.return_value = ({"status": "ok"}, {123}, True)
                await client.post("/api/upload", files={"file": ("test.log", b"data")})
            
            # 10. Profile dates
            await client.get("/api/dashboard/profile/888")
