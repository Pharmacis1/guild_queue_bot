import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import User, Character, Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check_player():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Players with User ID 53 ---")
        res_p = await session.execute(select(Player).filter(Player.user_id == 53))
        players = res_p.scalars().all()
        for p in players:
            nick_safe = p.nickname.encode('utf-8', 'replace').decode('utf-8') if p.nickname else "None"
            print(f"  Role ID: {p.role_id}, Nick: {nick_safe}, In Clan: {p.in_clan}")

        print("\n--- Characters linked to User ID 53 ---")
        res_c = await session.execute(select(Character).filter(Character.user_id == 53))
        chars = res_c.scalars().all()
        for c in chars:
            nick_safe = c.nickname.encode('utf-8', 'replace').decode('utf-8')
            print(f"  ID: {c.id}, Nick: {nick_safe}, Is Main: {c.is_main}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_player())
