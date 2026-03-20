import pytest
from sqlalchemy import select
from database import Event, Player
from logic.log_importer import process_log_upload
from httpx import AsyncClient, ASGITransport
from main import app
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_importer_deduplication(async_test_session):
    # Mock parse_board_file to return a specific event
    fake_data = [
        {
            "role_id": 100,
            "timestamp": 12345678,
            "date": "2024-03-20 12:00:00",
            "action_type": 1,
            "description": "Test Event",
            "raw_params": "50,0,0"
        }
    ]
    
    with patch("logic.log_importer.parse_board_file", return_value=fake_data):
        # First import
        res1, missing, should_run = await process_log_upload("dummy.log")
        assert res1["new_events"] == 1
        
        # Verify it's in DB
        stmt = select(Event).filter_by(role_id=100)
        result = await async_test_session.execute(stmt)
        assert len(result.scalars().all()) == 1
        
        # Second import (exact same data)
        res2, missing, should_run = await process_log_upload("dummy.log")
        assert res2["new_events"] == 0 # Should be skipped
        
        # Verify still only 1 in DB
        result = await async_test_session.execute(stmt)
        assert len(result.scalars().all()) == 1

@pytest.mark.asyncio
async def test_api_add_event_deduplication(async_test_session):
    payload = {"role_id": 200, "date": "2024-03-20 12:00:00", "value": 100}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # First add
        resp1 = await ac.post("/api/add_event", json=payload)
        assert resp1.status_code == 200
        assert "Event added" in resp1.json()["message"]
        
        # Second add
        resp2 = await ac.post("/api/add_event", json=payload)
        assert resp2.status_code == 200
        assert "Duplicate event skipped" in resp2.json()["message"]
        
        # Verify only 1 in DB
        stmt = select(Event).filter_by(role_id=200)
        result = await async_test_session.execute(stmt)
        assert len(result.scalars().all()) == 1
