import aiosqlite
import asyncio

async def check_specific_event():
    async with aiosqlite.connect('guild_bot.db') as conn:
        # Find the event
        # Timestamp is likely UNIX, but I can search by event_date string if available, or approximate.
        # Screenshot date format: YYYY-MM-DD HH:MM:SS
        target_date = "2026-01-22 13:01:46"
        
        # We need to JOIN with players to find 'Disaster'
        # And JOIN with items to see the name
        sql = """
            SELECT e.event_date, p.nickname, e.value, i.name, e.raw_desc
            FROM events e
            JOIN players p ON e.role_id = p.role_id
            LEFT JOIN items i ON e.value = i.id
            WHERE p.nickname = 'Disaster'
            AND e.event_date LIKE '2026-01-22 13:01%'
        """
        cursor = await conn.execute(sql)
        rows = await cursor.fetchall()
        print(f"Found {len(rows)} events:")
        for r in rows:
            print(f"Date: {r[0]}, Nick: {r[1]}, ItemID: {r[2]}, ItemName: {r[3]}, RawDesc: {r[4]}")
            # Also print the raw bytes of the name if possible (repr)
            if r[3]:
                print(f"Repr: {repr(r[3])}")

asyncio.run(check_specific_event())
