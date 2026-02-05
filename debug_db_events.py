import asyncio

import aiosqlite

DB_NAME = "guild_bot.db"

async def main():
    async with aiosqlite.connect(DB_NAME) as conn:
        print("--- LAST 10 EVENTS ---")
        async with conn.execute("""
            SELECT e.id, e.timestamp, e.event_date, e.event_type, e.value, e.raw_desc, i.name
            FROM events e
            LEFT JOIN items i ON e.value = i.id AND e.event_type = 0
            ORDER BY e.timestamp DESC
            LIMIT 10
        """) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                print(f"ID: {r[0]} | Date: {r[2]} | Type: {r[3]} | Val: {r[4]} | ItemName: {r[6]} | Desc: {r[5]}")

        print("\n--- ITEM COUNT ---")
        async with conn.execute("SELECT count(*) FROM items") as cursor:
            count = await cursor.fetchone()
            print(f"Items in DB: {count[0]}")

if __name__ == "__main__":
    asyncio.run(main())
