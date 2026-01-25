import sys
import os
import aiosqlite
import asyncio

# Add project root to sys.path
sys.path.append(os.getcwd())

from web_database import DB_NAME

async def inspect():
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute("SELECT * FROM players WHERE role_id = 1")
        row = await cursor.fetchone()
        if row:
            print(f"[OK] Found Player with ID 1: {row}")
        else:
            print("[FAIL] Player with ID 1 NOT found.")

        # Also check count
        cursor = await conn.execute("SELECT count(*) FROM players")
        count = (await cursor.fetchone())[0]
        print(f"Total players: {count}")

if __name__ == "__main__":
    asyncio.run(inspect())
