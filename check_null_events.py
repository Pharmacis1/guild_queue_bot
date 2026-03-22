import asyncio
import os
import sys
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database import Event, Player

DATABASE_URL = "postgresql+asyncpg://guild_user:G4N1V9R3@localhost/guild_bot"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    sys.stdout.reconfigure(encoding='utf-8')
    
    async with async_session() as session:
        # Get all Role IDs with NULL names
        res_null = await session.execute(select(Player.role_id).filter(Player.nickname.is_(None)))
        null_rids = [r for r in res_null.scalars()]
        
        print(f"--- Checking events for {len(null_rids)} NULL-named roles ---")
        if not null_rids: return
        
        # Get count of events for each
        stmt = (
            select(Event.role_id, func.count(Event.id))
            .where(Event.role_id.in_(null_rids))
            .group_by(Event.role_id)
            .order_by(func.count(Event.id).desc())
        )
        res_counts = await session.execute(stmt)
        for rid, count in res_counts.all():
            print(f"RoleID: {rid}, Event Count: {count}")
            # Show last 2 events for the most active one
            if count > 0:
                res_e = await session.execute(select(Event).filter(Event.role_id == rid).order_by(Event.timestamp.desc()).limit(2))
                for e in res_e.scalars():
                    print(f"  [{rid}] Date: {e.event_date}, Type: {e.event_type}, Val: {e.value}, Desc: {e.raw_desc}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
