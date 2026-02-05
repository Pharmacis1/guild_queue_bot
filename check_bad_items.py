import asyncio

import aiosqlite


async def search_bad_items():
    async with aiosqlite.connect('guild_bot.db') as conn:
        # Search for names starting with 'Р' (Cyrillic Er, which is 0xD0 in CP1251, start of UTF-8 2-byte sequence)
        cursor = await conn.execute("SELECT id, name FROM items WHERE name LIKE 'Р%' LIMIT 20")
        rows = await cursor.fetchall()
        print(f"Found {len(rows)} suspicious items:")
        for r in rows:
            print(f"ID: {r[0]}, Name: {r[1]}")

asyncio.run(search_bad_items())
