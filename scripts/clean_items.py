import asyncio

import aiosqlite

DB_NAME = "guild_bot.db"

async def main():
    async with aiosqlite.connect(DB_NAME) as conn:
        print("Cleaning 'Perfect World' from items table...")
        async with conn.execute("DELETE FROM items WHERE name = 'Perfect World'") as cursor:
            print(f"Deleted {cursor.rowcount} rows.")
        await conn.commit()

if __name__ == "__main__":
    asyncio.run(main())
