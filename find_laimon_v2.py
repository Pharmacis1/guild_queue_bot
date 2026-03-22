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
    
    # Configure stdout for UTF-8
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        print("--- Searching for 'Лаймон' ---")
        
        # Search in Player table
        res_players = await session.execute(select(Player).filter(Player.nickname.ilike("%Лаймон%")))
        players = res_players.scalars().all()
        print(f"Found in 'players' table: {len(players)}")
        for p in players:
            # Use repr for nickname to avoid encoding issues if reconfigure fails
            nick_safe = p.nickname.encode('utf-8', 'replace').decode('utf-8')
            print(f"  Role ID: {p.role_id}, Nick: {nick_safe}, User ID: {p.user_id}, Is Alt: {p.is_alt}, In Clan: {p.in_clan}")

        # Search in Character table
        res_chars = await session.execute(select(Character).filter(Character.nickname.ilike("%Лаймон%")))
        chars = res_chars.scalars().all()
        print(f"Found in 'characters' table: {len(chars)}")
        for c in chars:
            nick_safe = c.nickname.encode('utf-8', 'replace').decode('utf-8')
            print(f"  ID: {c.id}, Nick: {nick_safe}, User ID: {c.user_id}, Is Main: {c.is_main}")

        # Search in User table (by username)
        res_users = await session.execute(select(User).filter(User.username.ilike("%Лаймон%")))
        users = res_users.scalars().all()
        print(f"Found in 'users' table (username): {len(users)}")
        for u in users:
            name_safe = u.username.encode('utf-8', 'replace').decode('utf-8') if u.username else "None"
            print(f"  ID: {u.id}, TG ID: {u.telegram_id}, Name: {name_safe}")

        if not players and not chars and not users:
            print("No records found with name 'Лаймон'.")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_player())
