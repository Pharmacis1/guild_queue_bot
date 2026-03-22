import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import User, Character, Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check_player():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        print("--- Searching for 'Лаймон' ---")
        
        # Search in Player table
        res_players = await session.execute(select(Player).filter(Player.nickname.ilike("%Лаймон%")))
        players = res_players.scalars().all()
        print(f"Found in 'players' table: {len(players)}")
        for p in players:
            print(f"  Role ID: {p.role_id}, Nick: {p.nickname}, User ID: {p.user_id}, Is Alt: {p.is_alt}")

        # Search in Character table
        res_chars = await session.execute(select(Character).filter(Character.nickname.ilike("%Лаймон%")))
        chars = res_chars.scalars().all()
        print(f"Found in 'characters' table: {len(chars)}")
        for c in chars:
            print(f"  ID: {c.id}, Nick: {c.nickname}, User ID: {c.user_id}, Is Main: {c.is_main}")

        # Search in User table (by username)
        res_users = await session.execute(select(User).filter(User.username.ilike("%Лаймон%")))
        users = res_users.scalars().all()
        print(f"Found in 'users' table (username): {len(users)}")
        for u in users:
            print(f"  ID: {u.id}, TG ID: {u.telegram_id}, Name: {u.username}")

        if not players and not chars and not users:
            print("No records found with name 'Лаймон'.")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_player())
