import asyncio
import os
import sys
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Event, Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Searching for events with character name 'Лаймон' ---")
        # In history_data, name is func.coalesce(Player.nickname, "ID " + func.cast(Event.role_id, String))
        # But here we want to see if there were events for a role_id that ONCE had the name 'Лаймон'
        
        # 1. Search for any events that have 'Лаймон' in raw_desc (some events might have it)
        res_desc = await session.execute(select(Event).filter(Event.raw_desc.ilike("%Лаймон%")).limit(10))
        for e in res_desc.scalars():
            print(f"RoleID: {e.role_id}, Date: {e.event_date}, Desc: {e.raw_desc}")

        # 2. Search for any Player who has nickname 'Лаймон' (exact) again, but check for all entries
        res_p = await session.execute(select(Player).filter(func.trim(Player.nickname) == "Лаймон"))
        p_exact = res_p.scalars().all()
        print(f"\nExact matches in players table: {len(p_exact)}")
        for p in p_exact:
             print(f"RoleID: {p.role_id}, Nick: '{p.nickname}', InClan: {p.in_clan}")

        # 3. Check for any record with Role ID that might be it
        # Try to find if there's a player with no name but many events?
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
