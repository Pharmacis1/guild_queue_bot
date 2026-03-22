import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- All players with 'Лаймон' substring (HEX CHECK) ---")
        res = await session.execute(select(Player).filter(Player.nickname.ilike("%Лаймон%")))
        for p in res.scalars():
            nick = p.nickname
            nick_hex = nick.encode('utf-8').hex()
            print(f"RoleID: {p.role_id}, Nick: {nick!r}, Hex: {nick_hex}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
