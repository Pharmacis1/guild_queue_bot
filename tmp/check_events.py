import asyncio
import os
import sys
sys.path.append(os.getcwd())
from database import AsyncSessionLocal, CharacterEvent
from sqlalchemy import select, desc

async def check_events():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CharacterEvent).order_by(desc(CharacterEvent.created_at)).limit(5)
        )
        events = result.scalars().all()
        if not events:
            print("No events found in DB")
            return
        for e in events:
            print(f"[{e.created_at}] Event: {e.event_type} - {e.description}")

if __name__ == "__main__":
    asyncio.run(check_events())
