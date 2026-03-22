import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import QueueEntry

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Queue entries for User 53 ---")
        res = await session.execute(select(QueueEntry).filter(QueueEntry.user_id == 53))
        for q in res.scalars():
            char_name = q.character_name.encode('utf-8', 'replace').decode('utf-8') if q.character_name else "None"
            print(f"Queue ID: {q.id}, Type ID: {q.queue_type_id}, Char: {char_name}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
