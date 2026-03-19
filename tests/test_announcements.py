import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
from main import app
from database import User, Player, ScheduledAnnouncement
from handlers.admin import run_broadcast, schedule_job

@pytest.mark.asyncio
async def test_api_get_announcements(async_test_session):
    # Add some announcements
    ann1 = ScheduledAnnouncement(text="Active", schedule_type="daily", run_time="12:00", is_active=True)
    ann2 = ScheduledAnnouncement(text="Inactive", schedule_type="now", run_time="now", is_active=False)
    async_test_session.add_all([ann1, ann2])
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/master/announcements")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["announcements"]) == 1
        assert data["announcements"][0]["text"] == "Active"

@pytest.mark.asyncio
async def test_api_create_announce_now(async_test_session):
    with patch("handlers.admin.run_broadcast", new_callable=AsyncMock) as mock_run:
        payload = {"text": "Hello Now", "schedule_type": "now"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/master/announce", json=payload)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            
            # Check DB
            from database import select
            res = await async_test_session.execute(select(ScheduledAnnouncement).filter_by(text="Hello Now"))
            ann = res.scalar_one_or_none()
            assert ann is not None
            assert ann.is_active is True
            # Check mock
            mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_api_create_announce_future(async_test_session):
    with patch("handlers.admin.schedule_job") as mock_schedule:
        payload = {
            "text": "Hello Future", 
            "schedule_type": "once_future", 
            "run_time": "15.04.2024 14:00"
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/master/announce", json=payload)
            assert response.status_code == 200
            
            from database import select
            res = await async_test_session.execute(select(ScheduledAnnouncement).filter_by(text="Hello Future"))
            ann = res.scalar_one_or_none()
            assert ann is not None
            mock_schedule.assert_called_once()

@pytest.mark.asyncio
async def test_api_delete_announcement(async_test_session):
    ann = ScheduledAnnouncement(id=99, text="To Delete", schedule_type="daily", run_time="12:00", is_active=True)
    async_test_session.add(ann)
    await async_test_session.commit()

    with patch("loader.scheduler.remove_job") as mock_remove:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/master/announcements/delete", json={"id": 99})
            assert response.status_code == 200
            
            # Check deactivation
            await async_test_session.refresh(ann)
            assert ann.is_active is False
            mock_remove.assert_called_with("ann_99")

@pytest.mark.asyncio
async def test_run_broadcast_filtering(async_test_session):
    # Setup users and players
    # User 1: Has character in clan
    u1 = User(id=1, telegram_id=111, username="clan_user")
    p1 = Player(role_id=1, user_id=1, nickname="ClanMember", in_clan=1)
    
    # User 2: Has character NOT in clan
    u2 = User(id=2, telegram_id=222, username="non_clan_user")
    p2 = Player(role_id=2, user_id=2, nickname="NonClanMember", in_clan=0)
    
    # User 3: No characters
    u3 = User(id=3, telegram_id=333, username="no_char_user")
    
    ann = ScheduledAnnouncement(id=1, text="Guild News", schedule_type="now", is_active=True)
    
    async_test_session.add_all([u1, p1, u2, p2, u3, ann])
    await async_test_session.commit()

    mock_bot = AsyncMock()
    
    await run_broadcast(1, mock_bot)
    
    # Check that only User 1 received the message
    assert mock_bot.send_message.call_count == 1
    args, kwargs = mock_bot.send_message.call_args
    assert args[0] == 111
    assert "Guild News" in args[1]

@pytest.mark.asyncio
async def test_run_broadcast_deactivation(async_test_session):
    ann = ScheduledAnnouncement(id=5, text="Once", schedule_type="once_future", is_active=True)
    u = User(id=10, telegram_id=100)
    p = Player(role_id=10, user_id=10, in_clan=1)
    async_test_session.add_all([ann, u, p])
    await async_test_session.commit()

    mock_bot = AsyncMock()
    await run_broadcast(5, mock_bot)
    
    # Refresh from DB
    await async_test_session.refresh(ann)
    assert ann.is_active is False

@pytest.mark.asyncio
async def test_run_broadcast_empty_text(async_test_session):
    # Testing that it doesn't crash on empty text (though HTML will be weird)
    ann = ScheduledAnnouncement(id=6, text=None, schedule_type="now", is_active=True)
    u = User(id=11, telegram_id=101)
    p = Player(role_id=11, user_id=11, in_clan=1)
    async_test_session.add_all([ann, u, p])
    await async_test_session.commit()

    mock_bot = AsyncMock()
    # Should not raise exception
    await run_broadcast(6, mock_bot)
    mock_bot.send_message.assert_called_once()
