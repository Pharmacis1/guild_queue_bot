from datetime import datetime, timedelta

import aiosqlite
import pytest

from web_database import get_data_from_db


@pytest.mark.asyncio
async def test_get_data_from_db(test_db_session):
    # test_db_session is the path to the temp DB (yielded from fixture)
    db_path = test_db_session
    
    # 1. Insert Mock Data
    async with aiosqlite.connect(db_path) as conn:
        # Create Player
        await conn.execute("INSERT INTO players (role_id, nickname, in_clan, class_id) VALUES (?, ?, ?, ?)", 
                           (101, "TestPlayer", 1, 1))
        
        # Create Events
        today_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Timestamp needed for logic
        ts = int(datetime.now().timestamp())
        
        # Event type 1 (Valor), Value 100
        await conn.execute("INSERT INTO events (role_id, timestamp, event_date, event_type, value) VALUES (?, ?, ?, ?, ?)",
                           (101, ts, today_str, 1, 100))
        
        await conn.commit()

    # 2. Run functionality
    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    data, s, e, intervals = await get_data_from_db(start, today)
    
    # 3. Assertions
    assert len(data) == 1
    row = data[0]
    assert row['role_id'] == 101
    assert row['name'] == "TestPlayer"
    assert row['total_valor'] == 100

