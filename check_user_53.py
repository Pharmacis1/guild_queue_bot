import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import User

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check_user():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        res = await session.execute(select(User).filter_by(id=53))
        user = res.scalar_one_or_none()
        if user:
            print(f"User 53: ID={user.id}, TG={user.telegram_id}, Name={user.username}")
        else:
            print("User 53 not found.")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_user())
