import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import MessageLog

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Searching message logs for 'Лаймон' ---")
        res = await session.execute(select(MessageLog).filter(MessageLog.text.ilike("%Лаймон%")).order_by(MessageLog.timestamp.desc()).limit(20))
        for m in res.scalars():
            print(f"Date: {m.timestamp}, User: {m.user_name}, Text: {m.text}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
