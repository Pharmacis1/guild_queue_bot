import asyncio
import os
import sys
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Searching for NULL or empty nicknames ---")
        res_null = await session.execute(select(Player).filter(or_(Player.nickname.is_(None), Player.nickname == "")))
        for p in res_null.scalars():
             print(f"RoleID: {p.role_id}, Nick: {p.nickname}, UserID: {p.user_id}")

        print("\n--- Searching for Latin 'Laimon' ---")
        res_lat = await session.execute(select(Player).filter(Player.nickname.ilike("%Laimon%")))
        for p in res_lat.scalars():
             print(f"RoleID: {p.role_id}, Nick: {p.nickname}, UserID: {p.user_id}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
