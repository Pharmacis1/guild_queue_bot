
import aiosqlite
import asyncio
import os
import sys

# Add parent dir to path if needed (though usually run from root)
sys.path.append(os.getcwd())

from web_database import DB_NAME

async def fix_db():
    print(f"Connecting to {DB_NAME}...")
    async with aiosqlite.connect(DB_NAME) as conn:
        # 1. DELETE ID 1 (and other low IDs)
        print("Cleaning up invalid IDs (< 16)...")
        await conn.execute("DELETE FROM players WHERE role_id < 16")
        await conn.execute("DELETE FROM events WHERE role_id < 16")
        print("Invalid IDs removed.")

        # 2. Fix Kicked Players Status
        print("Fixing status of kicked players...")
        # Find all kick events (type 10)
        async with conn.execute("SELECT value, event_date FROM events WHERE event_type = 10") as cursor:
            kicked_events = await cursor.fetchall()
            
        kicked_ids = {row[0] for row in kicked_events if row[0] > 0}
        print(f"Found {len(kicked_ids)} players who were kicked: {kicked_ids}")
        
        if kicked_ids:
            placeholders = ','.join('?' for _ in kicked_ids)
            # Mark them as NOT in clan
            await conn.execute(f"UPDATE players SET in_clan = 0 WHERE role_id IN ({placeholders})", list(kicked_ids))
            print("Updated in_clan = 0 for kicked players.")

        await conn.commit()
        print("Done.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(fix_db())
