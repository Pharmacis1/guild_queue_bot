import asyncio
import os
import sys
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check_stats():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Count total players
        res_total = await session.execute(select(func.count(Player.role_id)))
        total = res_total.scalar()
        
        # Count linked players
        res_linked = await session.execute(select(func.count(Player.role_id)).where(Player.user_id.isnot(None)))
        linked = res_linked.scalar()
        
        print(f"Total players: {total}")
        print(f"Linked players: {linked}")
        
        if linked > 0:
            res_samp = await session.execute(select(Player).where(Player.user_id.isnot(None)).limit(5))
            for p in res_samp.scalars():
                print(f"  Role ID: {p.role_id}, User ID: {p.user_id}, Nick: {p.nickname}")
        else:
            print("No players have User ID set!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_stats())
