import asyncio

import aiosqlite


async def test_db():
    async with aiosqlite.connect('guild_bot.db') as conn:
        cursor = await conn.execute("SELECT id, name FROM items LIMIT 5")
        rows = await cursor.fetchall()
        for r in rows:
            print(f"ID: {r[0]}, Name: {r[1]}")

asyncio.run(test_db())
