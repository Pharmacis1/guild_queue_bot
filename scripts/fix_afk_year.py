"""Fix AFK dates with wrong year (2027 -> 2026)"""
import asyncio

import aiosqlite

DB_NAME = "guild_bot.db"

async def main():
    async with aiosqlite.connect(DB_NAME) as conn:
        # Find all users with AFK dates in 2027
        cursor = await conn.execute("""
            SELECT id, afk_start, afk_end 
            FROM users 
            WHERE afk_start LIKE '2027%' OR afk_end LIKE '2027%'
        """)
        rows = await cursor.fetchall()
        
        if not rows:
            print("No AFK dates with year 2027 found.")
            return
        
        print(f"Found {len(rows)} users with 2027 AFK dates:")
        for row in rows:
            uid, afk_start, afk_end = row
            print(f"  User ID: {uid}, Start: {afk_start}, End: {afk_end}")
        
        # Fix by replacing 2027 with 2026
        confirm = input("\nFix these by changing 2027 -> 2026? (y/n): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return
        
        for row in rows:
            uid, afk_start, afk_end = row
            new_start = afk_start.replace('2027', '2026') if afk_start else None
            new_end = afk_end.replace('2027', '2026') if afk_end else None
            
            await conn.execute("""
                UPDATE users 
                SET afk_start = ?, afk_end = ?
                WHERE id = ?
            """, (new_start, new_end, uid))
            print(f"  Fixed user {uid}: {new_start} - {new_end}")
        
        await conn.commit()
        print("\nDone! AFK dates fixed.")

if __name__ == "__main__":
    asyncio.run(main())
