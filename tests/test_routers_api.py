import pytest
import os
import io
import pytz
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import select, update, delete

from main import app
from database import User, Player, AFKHistory, QueueEntry, QueueType, Character, ConstantParty, Event

# -------------------------------------------------------------
# File operations
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_download_watcher_missing():
    with patch("os.path.exists", return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/download/watcher")
            assert response.status_code == 404

@pytest.mark.asyncio
async def test_download_watcher_exists():
    dummy_path = "dist/PW_Requiem_history.zip"
    os.makedirs("dist", exist_ok=True)
    with open(dummy_path, "wb") as f:
        f.write(b"dummy")
        
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/download/watcher")
        assert response.status_code == 200
    if os.path.exists(dummy_path):
        os.remove(dummy_path)

@pytest.mark.asyncio
async def test_upload_log():
    file_content = b"test log content"
    files = {"file": ("test.log", io.BytesIO(file_content), "text/plain")}
    
    with patch("routers.api.log_importer.process_log_upload", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = ({"status": "ok", "message": "Imported"}, [123], True)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/upload", files=files)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Player / AFK Endpoints
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_player_success(async_test_session):
    player = Player(role_id=1, nickname="Hero")
    async_test_session.add(player)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/get_player", json={"role_id": 1})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_afk_add_success(async_test_session):
    player = Player(role_id=1, nickname="Hero")
    async_test_session.add(player)
    await async_test_session.commit()

    payload = {"role_id": 1, "start": "2024-01-01", "end": "2024-01-02", "reason": "vacation"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/afk/add", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_afk_delete_success(async_test_session):
    # Use datetime objects for SQLAlchemy setup
    afk = AFKHistory(
        id=10, 
        role_id=1, 
        start_date=datetime(2024, 1, 1), 
        end_date=datetime(2024, 1, 2)
    )
    async_test_session.add(afk)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/afk/delete", json={"afk_id": 10})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Character Linking
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_character_link(async_test_session):
    user = User(id=1, telegram_id=123, username="test")
    async_test_session.add(user)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/character/link", json={"user_id": 1, "nickname": "Hero"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_character_unlink(async_test_session):
    player = Player(role_id=1, nickname="Hero", user_id=1)
    async_test_session.add(player)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/character/unlink", json={"role_id": 1})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Party Endpoints
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_party_add_member_success(async_test_session):
    party = ConstantParty(id=1, name="Squad")
    player = Player(role_id=1, nickname="Hero")
    async_test_session.add(party)
    async_test_session.add(player)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/party/add_member", json={"party_id": 1, "nickname": "Hero"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Update Endpoints
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_nickname(async_test_session):
    player = Player(role_id=1, nickname="Old")
    async_test_session.add(player)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/update_nickname", json={"role_id": 1, "nickname": "New"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_update_class(async_test_session):
    player = Player(role_id=1, class_id=1)
    async_test_session.add(player)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/update_class", json={"role_id": 1, "class_id": 2})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Event Endpoints
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_add_event(async_test_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {"role_id": 1, "date": "2024-01-01 12:00:00", "value": 50}
        response = await ac.post("/api/add_event", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_api_delete_event(async_test_session):
    # Use datetime objects for setup
    event = Event(role_id=1, timestamp=1000, event_date="2024-01-01 12:00:00")
    async_test_session.add(event)
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/delete_event", json={"role_id": 1, "timestamp": 1000})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

# -------------------------------------------------------------
# Scraper / Debug
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_scrape():
    with patch("routers.api.pwobs_scraper") as mock_scraper:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/scrape_players", json={"server": "capella"})
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_get_debug_screenshot():
    with patch("os.path.exists", return_value=True):
        with open("login_failed.png", "wb") as f: f.write(b"dummy")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/debug_screenshot")
            assert response.status_code == 200
        if os.path.exists("login_failed.png"):
            os.remove("login_failed.png")

@pytest.mark.asyncio
async def test_force_player_scan():
    with patch("scripts.pwobs_scraper.run_scraper", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/scan/players")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
