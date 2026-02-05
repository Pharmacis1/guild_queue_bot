import asyncio

import aiosqlite

DB_NAME = "guild_bot.db"

async def check_sync():
    async with aiosqlite.connect(DB_NAME) as conn:
        print("--- Checking #War ---")
        async with conn.execute("SELECT role_id, nickname, user_id FROM players WHERE nickname LIKE '%#War%'") as cursor:
            player = await cursor.fetchone()
            print(f"Player Table: {player}")

        async with conn.execute("SELECT id, user_id, nickname FROM characters WHERE nickname LIKE '%#War%'") as cursor:
            char = await cursor.fetchone()
            print(f"Character Table: {char}")

        if player and char:
            p_uid = player[2]
            c_uid = char[1]
            print(f"Match: {p_uid} == {c_uid} ? {p_uid == c_uid}")
            
            if c_uid:
                # Check user
                 async with conn.execute("SELECT id, telegram_id, username FROM users WHERE id = ?", (c_uid,)) as cursor:
                    user = await cursor.fetchone()
                    print(f"User Table: {user}")

if __name__ == "__main__":
    asyncio.run(check_sync())
