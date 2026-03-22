import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Event

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Recent Events for Role ID 586336 (★Лаймон☆) ---")
        res = await session.execute(select(Event).filter(Event.role_id == 586336).order_by(Event.timestamp.desc()).limit(5))
        for e in res.scalars():
            print(f"Date: {e.event_date}, Type: {e.event_type}, Val: {e.value}")

        print("\n--- Recent Events for Role ID 237328 (☆Лаймон☆) ---")
        res = await session.execute(select(Event).filter(Event.role_id == 237328).order_by(Event.timestamp.desc()).limit(5))
        for e in res.scalars():
            print(f"Date: {e.event_date}, Type: {e.event_type}, Val: {e.value}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
