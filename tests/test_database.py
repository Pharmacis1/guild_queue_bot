from datetime import datetime, timedelta

import aiosqlite
import pytest

from database import Player, Event
from web_database import get_data_from_db


@pytest.mark.asyncio
async def test_get_data_from_db(async_test_session):
    # 1. Insert Mock Data
    player = Player(role_id=101, nickname="TestPlayer", in_clan=1, class_id=1)
    async_test_session.add(player)
    
    # Create Events
    # Timestamp needed for logic
    now = datetime.now()
    ts = int(now.timestamp())
    today_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # Event type 1 (Valor), Value 100
    event = Event(role_id=101, timestamp=ts, event_date=today_str, event_type=1, value=100)
    async_test_session.add(event)
    
    await async_test_session.commit()

    # 2. Run functionality
    today = now.strftime("%Y-%m-%d")
    start = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    data, s, e, intervals = await get_data_from_db(start, today)
    
    print(f"DEBUG: Data length: {len(data)}")
    if data:
        print(f"DEBUG: First row: {data[0]}")
    
    assert len(data) > 0
    assert data[0]["role_id"] == 101

    # 3. Assertions
    assert len(data) == 1
    row = data[0]
    assert row["role_id"] == 101
    assert row["name"] == "TestPlayer"
    assert row["total_valor"] == 100
