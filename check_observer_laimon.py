import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import ObserverCache

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Searching observer_cache for 'Лаймон' ---")
        res = await session.execute(select(ObserverCache).filter(ObserverCache.html_content.ilike("%Лаймон%")))
        for c in res.scalars():
            print(f"RoleID: {c.role_id}, Updated at: {c.updated_at}")
            # We won't print HTML content as it might be large, but we found the ID!

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
