import asyncio

import aiosqlite

DB_NAME = "guild_bot.db"
CHECK_IDS = [48669, 67145, 59660, 67586, 67582, 67574, 58681]

async def main():
    async with aiosqlite.connect(DB_NAME) as conn:
        print(f"Checking {len(CHECK_IDS)} items...")
        placeholders = ",".join("?" * len(CHECK_IDS))
        async with conn.execute(f"SELECT id, name FROM items WHERE id IN ({placeholders})", CHECK_IDS) as cursor:
            rows = await cursor.fetchall()
            found = {r[0]: r[1] for r in rows}
            
            for iid in CHECK_IDS:
                if iid in found:
                    print(f"[OK] {iid}: {found[iid]}")
                else:
                    print(f"[MISSING] {iid}")

if __name__ == "__main__":
    asyncio.run(main())
