import asyncio
import os
import sys

import aiosqlite


# Mock Request
class MockRequest:
    def __init__(self, data):
        self._json = data

    async def json(self):
        return self._json


async def test_api():
    DB_NAME = "guild_bot.db"

    # 1. Setup Dummy Event
    role_id = 99999
    old_ts = 1700000000  # Some date
    old_date = "2023-11-14 23:06:40"  # UTC approx? No matter, string is what counts for UI

    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM events WHERE role_id = ?", (role_id,))
        await conn.execute(
            """
            INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
            VALUES (?, ?, ?, 0, 0, 'Test Event')
        """,
            (role_id, old_ts, old_date),
        )
        await conn.commit()

    print(f"Created event {role_id} at {old_date} ({old_ts})")

    # 2. Call API Logic (Importing function directly to avoid running server)
    sys.path.append(os.getcwd())
    from routers.api import update_event_date

    new_date_str = "2025-01-01 12:00:00"

    req = MockRequest({"role_id": role_id, "old_timestamp": old_ts, "new_date_str": new_date_str})

    print(f"Updating to {new_date_str}...")
    res = await update_event_date(req)
    print(f"API Result: {res}")

    # 3. Verify DB
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT event_date, timestamp FROM events WHERE role_id = ?", (role_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                print(f"DB Row: Date='{row[0]}', TS={row[1]}")
                if row[0] == new_date_str:
                    print("SUCCESS: Date updated.")
                else:
                    print("FAILURE: Date mismatch.")
            else:
                print("FAILURE: Event not found.")

    # Cleanup
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM events WHERE role_id = ?", (role_id,))
        await conn.commit()


if __name__ == "__main__":
    asyncio.run(test_api())
