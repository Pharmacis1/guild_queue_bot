import asyncio
import os
import sys
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def fix():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        print("--- Final fix for 'Лаймон' (Role 61136) ---")
        
        stmt = (
            update(Player)
            .where(Player.role_id == 61136)
            .values(in_clan=1, is_alt=True)
        )
        
        result = await session.execute(stmt)
        print(f"Updated {result.rowcount} player record (set InClan=1, IsAlt=True).")
        
        await session.commit()
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix())
