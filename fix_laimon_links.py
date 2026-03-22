import asyncio
import os
import sys
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def fix_links():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        print("--- Linking 'Лаймон' players to User 53 ---")
        
        # Nicknames found: ★Лаймон☆, ☆Лаймон☆, ★Лаймон★, AvGЛаймон
        nicks = ["★Лаймон☆", "☆Лаймон☆", "★Лаймон★", "AvGЛаймон"]
        
        stmt = (
            update(Player)
            .where(Player.nickname.in_(nicks))
            .values(user_id=53)
        )
        
        result = await session.execute(stmt)
        print(f"Updated {result.rowcount} players.")
        
        await session.commit()
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_links())
